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

Network: exactly ONE batched export.arxiv.org query call backfilling the
NULL-version paper rows (D9 sanctions this — metadata only; version-pinned
PDF URLs need it). Ids the API does not return keep a NULL version and fall
back to the unpinned URL (D9); the build never fails on backfill gaps.

Telemetry (D15): askrag.ingest.build_indexes run span with per-stage counts.
"""

import argparse
import json
import logging
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import chromadb
import chromadb.errors
import httpx

from askrag import telemetry
from askrag.config import get_settings
from askrag.ingest.embed_chunks import read_vectors

_log = logging.getLogger("askrag.ingest.build_indexes")

# Protocol facts, not tunables.
_EXPORT_ARXIV_QUERY_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_SEED_MEMBER = "arxiv-metadata-oai-snapshot.json"


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
            title=r["title"] or "",
            authors=r["authors"] or "",
            abstract=r["abstract"] or "",
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


def read_seed_licenses(seed_zip: Path, wanted_ids: set[str]) -> dict[str, str]:
    """One streaming pass over the Kaggle snapshot -> {arxiv_id: license URL}.

    Only non-null licenses are returned ("populated where the seed has it",
    issue #14 acceptance); the seed is 5+ GB uncompressed, so this never
    materializes it.
    """
    licenses: dict[str, str] = {}
    with zipfile.ZipFile(seed_zip) as zf, zf.open(_SEED_MEMBER) as fh:
        for raw in fh:
            record = json.loads(raw)
            arxiv_id = record.get("id", "")
            if arxiv_id in wanted_ids and record.get("license"):
                licenses[arxiv_id] = record["license"]
                if len(licenses) == len(wanted_ids):
                    break
    return licenses


def fetch_versions(
    ids: list[str],
    timeout_seconds: float,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str]:
    """ONE batched export.arxiv.org query -> {arxiv_id: latest version} (D9).

    `transport` is the test seam (httpx.MockTransport) — tests never touch
    the network.
    """
    if not ids:
        return {}
    with httpx.Client(transport=transport, timeout=timeout_seconds) as client:
        response = client.get(
            _EXPORT_ARXIV_QUERY_URL,
            params={"id_list": ",".join(ids), "max_results": len(ids)},
        )
        response.raise_for_status()
    versions: dict[str, str] = {}
    # Entity-expansion (billion-laughs) and XXE both require a DTD; Atom
    # never carries one, so a DTD here is an attack or a broken response —
    # refuse it instead of pulling in defusedxml for one offline call to a
    # pinned trusted host.
    if "<!DOCTYPE" in response.text:
        raise IndexBuildError("version backfill response contains a DTD — refusing to parse")
    root = ET.fromstring(response.text)  # noqa: S314 — DTD rejected above
    for entry in root.findall("atom:entry", _ATOM_NS):
        entry_id = entry.findtext("atom:id", "", _ATOM_NS)
        # Entry id ends ".../abs/<arxiv_id>v<N>"; the suffix is the latest version.
        tail = entry_id.rsplit("/", 1)[-1]
        arxiv_id, sep, version = tail.rpartition("v")
        if sep and arxiv_id in ids and version.isdigit():
            versions[arxiv_id] = f"v{version}"
    return versions


def _write_corpus_db(db_path: Path, papers: list[PaperRow], chunks: list[ChunkRow]) -> None:
    # tmp + rename: a killed build never leaves a half-written corpus.db that
    # a read-only server would then trust (same contract as every ingest stage).
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
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
                venue_rigor      INTEGER
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
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        conn.executemany(
            "INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
        conn.execute("INSERT INTO chunks_fts(rowid, text) SELECT rowid, text FROM chunks")
        # Snapshot stamp (D12): the footer's "corpus YYYY-MM" and ingest_stats
        # read this instead of guessing from file mtimes.
        built_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
        conn.executemany(
            "INSERT INTO meta VALUES (?,?)",
            [("built_at", built_at), ("snapshot", built_at[:7])],
        )
        conn.commit()
    finally:
        conn.close()
    tmp.replace(db_path)


def _load_chroma(
    chroma_dir: Path,
    collection_name: str,
    vectors_parquet: Path,
    chunks: list[ChunkRow],
    papers_by_id: dict[str, PaperRow],
    add_batch_size: int,
) -> int:
    """Per-model parquet -> a per-model Chroma collection; returns its count."""
    table = read_vectors(vectors_parquet, expected_slug=collection_name)
    ids = table["chunk_id"].to_pylist()
    vectors = table["vector"].to_pylist()
    chunks_by_id = {c.chunk_id: c for c in chunks}
    missing = [i for i in ids if i not in chunks_by_id]
    if missing:
        raise IndexBuildError(
            f"{len(missing)} embedded chunk_ids missing from chunks.jsonl "
            f"(first: {missing[0]}) — stale parquet or stale chunks?"
        )
    client = chromadb.PersistentClient(path=str(chroma_dir))
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
            embeddings=vectors[start : start + add_batch_size],
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
    chunks_path: Path,
    vectors_parquet: Path,
    seed_zip: Path,
    corpus_db: Path,
    chroma_dir: Path,
    collection_name: str,
    *,
    add_batch_size: int,
    backfill_timeout_seconds: float,
    backfill_transport: httpx.BaseTransport | None = None,
) -> BuildStats:
    """Rebuild corpus.db + the per-model Chroma collection from ingest artifacts."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = BuildStats()
    with tracer.start_as_current_span("askrag.ingest.build_indexes") as span:
        papers = _read_papers(arxiv_db)
        chunks = _read_chunks(chunks_path)
        stats.papers, stats.chunks = len(papers), len(chunks)

        licenses = read_seed_licenses(seed_zip, {p.arxiv_id for p in papers})
        stats.licenses_found = len(licenses)

        null_version_ids = [p.arxiv_id for p in papers if not p.version]
        backfilled = fetch_versions(
            null_version_ids, backfill_timeout_seconds, transport=backfill_transport
        )
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

        _write_corpus_db(corpus_db, papers, chunks)
        stats.chroma_count = _load_chroma(
            chroma_dir, collection_name, vectors_parquet, chunks, papers_by_id, add_batch_size
        )

        # THE acceptance invariant (issue #14): the two stores hold the same
        # chunk set or the artifact pair is not shippable.
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

    _log.info(
        f"build_indexes: {stats.papers} papers, {stats.chunks} chunks -> {corpus_db.name} "
        f"+ chroma '{collection_name}' ({stats.chroma_count}); "
        f"versions backfilled {stats.versions_backfilled} (missing {stats.versions_missing}), "
        f"licenses {stats.licenses_found}"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    try:
        run(
            arxiv_db=settings.arxiv_db_path,
            chunks_path=settings.chunks_jsonl_path,
            vectors_parquet=settings.vectors_parquet_path,
            seed_zip=settings.kaggle_seed_path,
            corpus_db=settings.corpus_db_path,
            chroma_dir=settings.chroma_dir,
            collection_name=settings.embedding_model_slug,
            add_batch_size=settings.chroma_add_batch_size,
            backfill_timeout_seconds=settings.version_backfill_timeout_seconds,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
