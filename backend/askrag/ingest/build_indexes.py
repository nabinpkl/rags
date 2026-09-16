"""chunks.jsonl + vectors/<slug>.parquet + arxiv.db -> corpus.db + chroma/ (D4).

The deployable index pair, rebuilt as one artifact so SQLite and Chroma can
never drift (D4 risk note): corpus.db holds `papers` (facets + license from
the Kaggle seed + version), `chunks`, and an FTS5 table over chunk text;
chroma/ holds the same chunk ids in a collection NAMED BY THE EMBEDDING MODEL
SLUG — the per-model keying contract from #13 (`read_vectors` refuses another
model's parquet, and two models' vectors land in two collections, never one).

Idempotent drop-and-rebuild by design (vertical-slice directive, issue #14):
indexes are derived artifacts — corpus.db is written to a tmp file and
renamed, the Chroma collection is deleted and recreated. No incremental
machinery.

Network: none. The build is fully offline: NULL-version paper rows backfill
from the Kaggle snapshot's `versions` array (D9 pinning without the former
batched export.arxiv.org query, retired under D18). Ids the snapshot does not
carry keep a NULL version and fall back to the unpinned URL (D9); the build
never fails on backfill gaps.

Telemetry (D15): askrag.ingest.build_indexes run span with per-stage counts.
"""

import argparse
import json
import logging
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

import chromadb
import chromadb.config
import chromadb.errors

from askrag import telemetry
from askrag.config import get_settings
from askrag.ingest import kaggle_seed
from askrag.ingest.embed_chunks import read_vectors
from askrag.ingest.extract_citations import read_citations
from askrag.ingest.latex_text import latex_to_text
from askrag.ingest.resolve_cited_works import CitedWorkRow, read_cited_works

_log = logging.getLogger("askrag.ingest.build_indexes")


class IndexBuildError(Exception):
    """The built indexes violate an invariant (count mismatch, bad input)."""


@dataclass(frozen=True)
class PaperRow:
    """One `papers` row: collector metadata + facets + §6b duties (license, version)."""

    arxiv_id: str
    title: str
    authors: str
    abstract: str
    categories: str
    published: str
    version: str | None
    license: str | None
    venue: str | None
    authority: float | None
    niche_idf: float | None
    author_novelty: float | None
    revisions: int | None
    venue_rigor: int | None
    # Did this paper's text reach the reference parser? The landing page's
    # parse rate is 16,893 of the 20,733 papers we EXTRACTED TEXT FROM (81%),
    # not of the 57,206 catalog rows we hold metadata for — quoting the
    # second denominator turned "never collected" into "failed to parse"
    # and printed 30% against ourselves.
    has_text: bool = False

    @property
    def primary_category(self) -> str:
        return self.categories.split()[0] if self.categories else ""

    @property
    def year(self) -> int:
        # `published` is ISO (collector-filled); the arxiv_id prefix YYMM is
        # the documented fallback for the handful of rows without it.
        if self.published:
            return int(self.published[:4])
        yy = int(self.arxiv_id[:2])
        return 1900 + yy if yy >= 90 else 2000 + yy


@dataclass(frozen=True)
class ChunkRow:
    """One `chunks` row (chunk_papers' record shape, #12)."""

    chunk_id: str
    paper_id: str
    section: str
    page_start: int
    page_end: int
    text: str
    n_tokens: int


@dataclass
class BuildStats:
    papers: int = 0
    chunks: int = 0
    versions_backfilled: int = 0
    versions_missing: int = 0
    licenses_found: int = 0
    chroma_count: int = 0
    cited_works: int = 0
    citations: int = 0
    papers_with_text: int = 0
    catalog_months: int = 0
    # Only a metadata-only build leaves this above zero: chunks written to
    # corpus.db that the vector store does not carry yet.
    chunks_without_vectors: int = 0


def _read_papers(arxiv_db: Path) -> list[PaperRow]:
    # arxiv.db is the collector's artifact — opened read-only, never written
    # (§4c boundary); corpus.db is where backfilled versions land.
    conn = sqlite3.connect(f"{arxiv_db.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT arxiv_id, title, authors, abstract, categories, published,"
            "       version, venue, authority, niche_idf, author_novelty,"
            "       revisions, venue_rigor FROM papers"
        ).fetchall()
    finally:
        conn.close()
    return [
        PaperRow(
            arxiv_id=r["arxiv_id"],
            # The catalog is LaTeX (latex_text.py); corpus.db is what the UI
            # and the agent read, so the conversion happens at THIS boundary
            # and arxiv.db keeps its source bytes.
            title=latex_to_text(r["title"] or ""),
            authors=latex_to_text(r["authors"] or ""),
            abstract=latex_to_text(r["abstract"] or ""),
            categories=r["categories"] or "",
            published=r["published"] or "",
            version=r["version"] or None,
            license=None,  # filled from the Kaggle seed below
            venue=r["venue"] or None,
            authority=r["authority"],
            niche_idf=r["niche_idf"],
            author_novelty=r["author_novelty"],
            revisions=r["revisions"],
            venue_rigor=r["venue_rigor"],
        )
        for r in rows
    ]


def _read_chunks(chunks_path: Path) -> list[ChunkRow]:
    chunks: list[ChunkRow] = []
    with chunks_path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            chunks.append(
                ChunkRow(
                    chunk_id=r["chunk_id"],
                    paper_id=r["paper_id"],
                    section=r["section"],
                    page_start=r["page_start"],
                    page_end=r["page_end"],
                    text=r["text"],
                    n_tokens=r["n_tokens"],
                )
            )
    return chunks


def read_extracted_text_ids(text_dir: Path) -> set[str]:
    """Which papers we hold extracted text for, from the tree the parser read.

    `extract_citations` globs this same tree, so this set IS the parser's
    input: every paper in it was offered to the reference parser, and every
    paper outside it never was. The page's parse rate needs that distinction
    (`PaperRow.has_text`) — 20,733 papers have text against 57,206 catalog
    rows, and using the catalog as the denominator reported a 30% parse rate
    for a parser that actually yields 81%.
    """
    if not text_dir.exists():
        return set()
    return {path.stem for path in text_dir.glob("*/*.txt")}


def read_seed_licenses(seed_zip: Path, wanted_ids: set[str]) -> dict[str, str]:
    """One streaming pass over the Kaggle snapshot -> {arxiv_id: license URL}.

    Only non-null licenses are returned ("populated where the seed has it",
    issue #14 acceptance); the seed is 5+ GB uncompressed, so this never
    materializes it.
    """
    return {
        record["id"]: record["license"]
        for record in kaggle_seed.iter_records(seed_zip, wanted_ids)
        if record.get("license")
    }


def read_seed_versions(seed_zip: Path, wanted_ids: set[str]) -> dict[str, str]:
    """{arxiv_id: latest version} for NULL-version rows, from the snapshot (D18).

    Local early-exit lookup: seconds for a handful of ids, no network, so a
    throttled arXiv can never gate a local build again.
    """
    versions: dict[str, str] = {}
    for record in kaggle_seed.iter_records(seed_zip, wanted_ids):
        version = kaggle_seed.latest_version(record)
        if version:
            versions[record["id"]] = version
    return versions


def _write_corpus_db(
    db_path: Path,
    papers: list[PaperRow],
    chunks: list[ChunkRow],
    cited_works: Sequence[CitedWorkRow] = (),
    citations: Sequence[tuple[str, str]] = (),
    catalog_months: Mapping[str, int] = MappingProxyType({}),
) -> None:
    """Write the deployable corpus.db.

    The citation tables default to empty because a corpus built before
    extract_citations ran is a legitimate (landing-page-less) artifact, not a
    caller mistake — `run` always passes them explicitly.
    """
    # tmp + rename: a killed build never leaves a half-written corpus.db that
    # a read-only server would then trust (same contract as every ingest stage).
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        # SQLite FKs are OFF by default, which would make the schema's
        # REFERENCES clause decorative; _validate_inputs already guarantees
        # referential integrity, this makes the schema enforce it too.
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE papers (
                arxiv_id         TEXT PRIMARY KEY,
                title            TEXT NOT NULL,
                authors          TEXT NOT NULL,
                abstract         TEXT NOT NULL,
                categories       TEXT NOT NULL,
                primary_category TEXT NOT NULL,
                year             INTEGER NOT NULL,
                published        TEXT NOT NULL,
                version          TEXT,           -- NULL => unpinned PDF URL fallback (D9)
                license          TEXT,           -- NULL => seed had none (§6b)
                venue            TEXT,
                authority        REAL,
                niche_idf        REAL,
                author_novelty   REAL,
                revisions        INTEGER,
                venue_rigor      INTEGER,
                -- 1 => we extracted this paper's text, so it reached the
                -- reference parser. The parse rate on the landing page is
                -- counted over these rows, never over every catalog row.
                has_text         INTEGER NOT NULL
            );
            -- Title and abstract of EVERY paper, indexed or not: the catalog
            -- filter (/api/catalog) searches the whole table, and the Kaggle
            -- snapshot carries an abstract for every row, so this is the one
            -- text surface that does not depend on having extracted a PDF.
            -- Separate from chunks_fts, which indexes retrieved chunk text and
            -- exists only for the 811 papers the agent can read (D16).
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                title, abstract, content=papers, content_rowid=rowid,
                tokenize='porter unicode61'
            );
            CREATE TABLE chunks (
                chunk_id   TEXT PRIMARY KEY,
                paper_id   TEXT NOT NULL REFERENCES papers(arxiv_id),
                section    TEXT NOT NULL,
                page_start INTEGER NOT NULL,
                page_end   INTEGER NOT NULL,
                text       TEXT NOT NULL,
                n_tokens   INTEGER NOT NULL
            );
            CREATE INDEX chunks_paper_id ON chunks(paper_id);
            -- External-content FTS5: BM25 over chunk text without storing it
            -- twice; rowid joins back to chunks (D4).
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text, content=chunks, content_rowid=rowid, tokenize='porter unicode61'
            );
            -- Catalog metadata for works our papers CITE. Separate from
            -- `papers` on purpose: a `papers` row means we hold the text and
            -- can retrieve it, a `cited_works` row means we know only what the
            -- Kaggle catalog says. Merging them would let a work nothing can
            -- read surface wherever a readable paper can.
            CREATE TABLE cited_works (
                arxiv_id         TEXT PRIMARY KEY,
                title            TEXT,           -- NULL => catalog had no record
                authors          TEXT,
                primary_category TEXT,
                year             INTEGER,
                version          TEXT            -- NULL => unpinned arxiv.org URL (D9)
            );
            CREATE TABLE citations (
                citing_id TEXT NOT NULL REFERENCES papers(arxiv_id),
                cited_id  TEXT NOT NULL REFERENCES cited_works(arxiv_id),
                PRIMARY KEY (citing_id, cited_id)
            ) WITHOUT ROWID;
            -- The landing page's every query reads by cited_id ("who cites
            -- this?"); the PK already covers the citing_id direction.
            CREATE INDEX citations_cited ON citations(cited_id);
            -- There is deliberately NO (arxiv_id, year) covering index on
            -- cited_works. One was tried for the cited-year histogram and
            -- measured on a quiet box (2026-08-28, 162k edges): without
            -- ANALYZE the planner ignored it entirely (110 ms either way);
            -- with ANALYZE it used it and still bought nothing (91.3 vs
            -- 91.4 ms). The 17% that ANALYZE below does buy comes from the
            -- join order, not from any index. Re-measure before adding one.

            -- How many cs papers the Kaggle catalog lists per id-month: the
            -- DENOMINATOR the landing page had no way to state. Without it
            -- the page said "every cs paper arXiv posted", which measured
            -- 94% for July 2026, 49% for August and 5% for September.
            -- Catalog-wide, not scoped to what we hold, and cs-primary to
            -- match how the collector selected papers.
            CREATE TABLE catalog_months (
                month     TEXT PRIMARY KEY,   -- id-month, e.g. "2607"
                cs_papers INTEGER NOT NULL
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        conn.executemany(
            "INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.arxiv_id,
                    p.title,
                    p.authors,
                    p.abstract,
                    p.categories,
                    p.primary_category,
                    p.year,
                    p.published,
                    p.version,
                    p.license,
                    p.venue,
                    p.authority,
                    p.niche_idf,
                    p.author_novelty,
                    p.revisions,
                    p.venue_rigor,
                    int(p.has_text),
                )
                for p in papers
            ],
        )
        conn.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?,?)",
            [
                (c.chunk_id, c.paper_id, c.section, c.page_start, c.page_end, c.text, c.n_tokens)
                for c in chunks
            ],
        )
        conn.execute(
            "INSERT INTO papers_fts(rowid, title, abstract)"
            " SELECT rowid, title, abstract FROM papers"
        )
        conn.execute("INSERT INTO chunks_fts(rowid, text) SELECT rowid, text FROM chunks")
        # cited_works before citations: the FK on cited_id is enforced (PRAGMA
        # foreign_keys=ON above), so the referenced rows must already exist.
        conn.executemany(
            "INSERT INTO cited_works VALUES (?,?,?,?,?,?)",
            [
                (w.arxiv_id, w.title, w.authors, w.primary_category, w.year, w.version)
                for w in cited_works
            ],
        )
        conn.executemany("INSERT INTO citations VALUES (?,?)", citations)
        conn.executemany("INSERT INTO catalog_months VALUES (?,?)", sorted(catalog_months.items()))
        # Snapshot stamp (D12): the footer's "corpus YYYY-MM" and ingest_stats
        # read this instead of guessing from file mtimes.
        built_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [("built_at", built_at), ("snapshot", built_at[:7])],
        )
        # Without stats the planner drives the cited-year histogram from the
        # citations side and takes 110 ms; with them it flips the join and
        # takes 91 ms (measured 2026-08-28). The snapshot is frozen (D12), so
        # these stats never go stale between builds.
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()
    tmp.replace(db_path)


def _validate_inputs(
    chunk_ids_embedded: list[str],
    chunks: list[ChunkRow],
    papers_by_id: dict[str, PaperRow],
    cited_works: Sequence[CitedWorkRow] = (),
    citations: Sequence[tuple[str, str]] = (),
    *,
    require_every_chunk_embedded: bool = True,
) -> None:
    """Every input invariant, checked BEFORE any artifact is written.

    A failed build must leave the previous corpus.db + chroma generation
    untouched (review finding #55-1): validate-then-write, never the reverse.
    `read_vectors`' slug/provenance refusal runs earlier still, at read time.
    """
    dangling_citing = sorted({a for a, _ in citations} - papers_by_id.keys())
    if dangling_citing:
        raise IndexBuildError(
            f"{len(dangling_citing)} citation(s) come from a paper missing in arxiv.db "
            f"(first: {dangling_citing[0]}) — citations.tsv built from a different "
            "text tree than the collector db?"
        )
    dangling_cited = sorted({b for _, b in citations} - {w.arxiv_id for w in cited_works})
    if dangling_cited:
        raise IndexBuildError(
            f"{len(dangling_cited)} cited id(s) missing from cited_works.jsonl "
            f"(first: {dangling_cited[0]}) — stale cited_works, rerun resolve_cited_works"
        )
    orphans = sorted({c.paper_id for c in chunks} - papers_by_id.keys())
    if orphans:
        raise IndexBuildError(
            f"{len(orphans)} chunk paper_id(s) missing from arxiv.db "
            f"(first: {orphans[0]}) — collector db rebuilt or pruned after extraction?"
        )
    chunk_ids = {c.chunk_id for c in chunks}
    missing = [i for i in chunk_ids_embedded if i not in chunk_ids]
    if missing:
        raise IndexBuildError(
            f"{len(missing)} embedded chunk_ids missing from chunks.jsonl "
            f"(first: {missing[0]}) — stale parquet or stale chunks?"
        )
    if require_every_chunk_embedded and len(chunk_ids_embedded) != len(chunks):
        raise IndexBuildError(
            f"vectors parquet holds {len(chunk_ids_embedded)} vectors but chunks.jsonl "
            f"holds {len(chunks)} chunks — re-run embed_chunks before indexing"
        )


def _load_chroma(
    chroma_dir: Path,
    collection_name: str,
    ids: list[str],
    vectors: list[list[float]],
    chunks_by_id: dict[str, ChunkRow],
    papers_by_id: dict[str, PaperRow],
    add_batch_size: int,
) -> int:
    """Pre-validated vectors -> the per-model Chroma collection; returns its count."""
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        # The pinned 1.5.9 ships a no-op telemetry client (verified in review),
        # but no-egress must be deliberate, not an accident of the pin.
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(collection_name)  # drop-and-rebuild
    except chromadb.errors.NotFoundError:  # first build — nothing to drop
        pass
    collection = client.create_collection(
        collection_name,
        # Cosine over unit-normalized vectors (embed_chunks normalizes both
        # backends); metadata fields power `where` filters in hybrid search.
        configuration={"hnsw": {"space": "cosine"}},
    )
    for start in range(0, len(ids), add_batch_size):
        batch_ids = ids[start : start + add_batch_size]
        collection.add(
            ids=batch_ids,
            # cast only widens list[list[float]] to what chroma declares;
            # list invariance blocks the direct assignment.
            embeddings=cast("list[Sequence[float]]", vectors[start : start + add_batch_size]),
            metadatas=[
                {
                    "paper_id": chunks_by_id[i].paper_id,
                    "category": papers_by_id[chunks_by_id[i].paper_id].primary_category,
                    "year": papers_by_id[chunks_by_id[i].paper_id].year,
                }
                for i in batch_ids
            ],
        )
    return collection.count()


def run(
    arxiv_db: Path,
    text_dir: Path,
    chunks_path: Path,
    vectors_parquet: Path,
    seed_zip: Path,
    corpus_db: Path,
    chroma_dir: Path,
    collection_name: str,
    *,
    add_batch_size: int,
    # Optional: a corpus built before extract_citations ran is a legitimate
    # (landing-page-less) artifact, so absent paths mean "no citation graph"
    # rather than a caller mistake.
    citations_path: Path | None = None,
    cited_works_path: Path | None = None,
    without_vectors: bool = False,
) -> BuildStats:
    """Rebuild corpus.db + the per-model Chroma collection from ingest artifacts.

    `without_vectors` rebuilds corpus.db ALONE and leaves the Chroma
    collection exactly as it is. It exists because the two artifacts age at
    different speeds: the page's numbers are metadata (papers, citations, the
    catalog census) and a month of new papers reaches them in minutes, while
    embedding those same papers is hours of CPU on this box (measured
    2026-09-16: ~1,000 chunks/hour). The cost is stated rather than hidden —
    chunks written without a vector are counted, logged, and searchable by
    keyword but not by vector until a full build runs. See DECISIONS.md
    2026-09-16.
    """
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = BuildStats()
    with tracer.start_as_current_span("askrag.ingest.build_indexes") as span:
        papers = _read_papers(arxiv_db)
        with_text = read_extracted_text_ids(text_dir)
        papers = [replace(p, has_text=p.arxiv_id in with_text) for p in papers]
        stats.papers_with_text = sum(1 for p in papers if p.has_text)
        chunks = _read_chunks(chunks_path)
        # The citation graph is optional input: a corpus built before
        # extract_citations ran still produces a valid (landing-page-less)
        # index pair, and says so rather than shipping silently empty tables.
        have_citations = citations_path is not None and citations_path.exists()
        citations = read_citations(citations_path) if have_citations else []
        cited_works = (
            read_cited_works(cited_works_path)
            if cited_works_path is not None and cited_works_path.exists()
            else []
        )
        if not citations:
            _log.warning(
                f"no citation edges at {citations_path or '<unset>'} — corpus.db will carry empty "
                "citations/cited_works tables and the landing page will have nothing to rank"
            )
        stats.papers, stats.chunks = len(papers), len(chunks)
        stats.citations, stats.cited_works = len(citations), len(cited_works)

        # ALL validation precedes any write or seed stage: a failed
        # build leaves the previous artifact generation untouched, and bad
        # inputs fail before the 5.4 GB seed pass (review finding #55-1).
        table = read_vectors(vectors_parquet, expected_slug=collection_name)
        embedded_ids = table["chunk_id"].to_pylist()
        _validate_inputs(
            embedded_ids,
            chunks,
            {p.arxiv_id: p for p in papers},
            cited_works,
            citations,
            require_every_chunk_embedded=not without_vectors,
        )

        licenses = read_seed_licenses(seed_zip, {p.arxiv_id for p in papers})
        stats.licenses_found = len(licenses)

        null_version_ids = {p.arxiv_id for p in papers if not p.version}
        backfilled = read_seed_versions(seed_zip, null_version_ids)
        stats.versions_backfilled = len(backfilled)
        stats.versions_missing = len(null_version_ids) - len(backfilled)
        if stats.versions_missing:
            _log.warning(
                f"{stats.versions_missing} paper(s) still lack a version after "
                "backfill — they fall back to unpinned PDF URLs (D9)"
            )

        papers = [
            replace(
                p,
                license=licenses.get(p.arxiv_id),
                version=p.version or backfilled.get(p.arxiv_id),
            )
            for p in papers
        ]
        papers_by_id = {p.arxiv_id: p for p in papers}

        # A FULL pass over the snapshot (~85 s), unlike the two targeted
        # lookups above: this is the catalog's own per-month total, so there
        # is no id set to stop early on. It runs after validation with the
        # other seed reads, never before them.
        catalog_months = kaggle_seed.count_cs_papers_by_id_month(seed_zip)
        stats.catalog_months = len(catalog_months)

        _write_corpus_db(corpus_db, papers, chunks, cited_works, citations, catalog_months)
        if without_vectors:
            stats.chunks_without_vectors = len(chunks) - len(set(embedded_ids))
            # Loud, because this is the one build that ships the two stores
            # out of step on purpose: a silent version of it would look like
            # a vector index that had quietly stopped finding new papers.
            _log.warning(
                f"metadata-only build: {stats.chunks_without_vectors} of {len(chunks)} chunks "
                f"have no vector yet. corpus.db is current; chroma '{collection_name}' is "
                "untouched, so those papers answer to keyword search only until a full "
                "build runs"
            )
        else:
            stats.chroma_count = _load_chroma(
                chroma_dir,
                collection_name,
                embedded_ids,
                table["vector"].to_pylist(),
                {c.chunk_id: c for c in chunks},
                papers_by_id,
                add_batch_size,
            )

            # THE acceptance invariant (issue #14): the two stores hold the
            # same chunk set or the artifact pair is not shippable.
            if stats.chroma_count != stats.chunks:
                raise IndexBuildError(
                    f"chunks table has {stats.chunks} rows but chroma collection "
                    f"'{collection_name}' has {stats.chroma_count}"
                )

        span.set_attribute("askrag.model_slug", collection_name)
        span.set_attribute("askrag.papers", stats.papers)
        span.set_attribute("askrag.chunks", stats.chunks)
        span.set_attribute("askrag.versions_backfilled", stats.versions_backfilled)
        span.set_attribute("askrag.versions_missing", stats.versions_missing)
        span.set_attribute("askrag.licenses_found", stats.licenses_found)
        span.set_attribute("askrag.cited_works", stats.cited_works)
        span.set_attribute("askrag.citations", stats.citations)
        span.set_attribute("askrag.papers_with_text", stats.papers_with_text)
        span.set_attribute("askrag.catalog_months", stats.catalog_months)

    _log.info(
        f"build_indexes: {stats.papers} papers, {stats.chunks} chunks -> {corpus_db.name} "
        f"+ chroma '{collection_name}' ({stats.chroma_count}); "
        f"versions backfilled {stats.versions_backfilled} (missing {stats.versions_missing}), "
        f"licenses {stats.licenses_found}; "
        f"{stats.citations} citations over {stats.cited_works} cited works; "
        f"{stats.papers_with_text} papers with extracted text, "
        f"catalog census over {stats.catalog_months} id-months"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--without-vectors",
        action="store_true",
        help="rebuild corpus.db alone, leaving the vector store as it is (see the run docstring)",
    )
    args = parser.parse_args(argv)
    try:
        run(
            arxiv_db=settings.arxiv_db_path,
            text_dir=settings.text_dir,
            chunks_path=settings.chunks_jsonl_path,
            vectors_parquet=settings.vectors_parquet_path,
            seed_zip=settings.kaggle_seed_path,
            citations_path=settings.citations_path,
            cited_works_path=settings.cited_works_path,
            corpus_db=settings.corpus_db_path,
            chroma_dir=settings.chroma_dir,
            collection_name=settings.embedding_model_slug,
            add_batch_size=settings.chroma_add_batch_size,
            without_vectors=args.without_vectors,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
