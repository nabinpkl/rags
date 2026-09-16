"""Tests for askrag.ingest.build_indexes — corpus.db + per-model chroma."""

import json
import sqlite3
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from askrag.ingest import build_indexes
from askrag.ingest.build_indexes import IndexBuildError
from askrag.ingest.embed_chunks import EmbeddingProvenance

DIMS = 4
SLUG = f"fake-embed_{DIMS}"

PROVENANCE = EmbeddingProvenance(
    model="fake/fake-embed",
    revision="deadbeef",
    dims=DIMS,
    backend="local",
    slug=SLUG,
    created_at="2026-07-05T00:00:00+00:00",
)

PAPERS = [
    # (arxiv_id, title, categories, published, version, venue)
    ("2401.00001", "Attention is enough", "cs.CL cs.AI", "2024-01-02", "v2", "ACL"),
    ("2401.00002", "Graphs at scale", "cs.DS", "2024-01-03", None, None),
    ("0704.0217", "Fading channels", "cs.IT", "", "v1", None),
]

CHUNKS = [
    ("2401.00001#0", "2401.00001", "Intro", 1, 1, "transformers use self attention", 5),
    ("2401.00001#1", "2401.00001", "Method", 2, 3, "we scale attention heads widely", 5),
    ("2401.00002#0", "2401.00002", "__paper__", 1, 1, "graph algorithms on huge inputs", 5),
]


_AXIS = {"2401.00001#0": 0, "2401.00001#1": 1, "2401.00002#0": 2}


def vector_for(chunk_id: str) -> list[float]:
    # One distinct axis per known chunk so nearest-neighbor is checkable;
    # NOT hash() — string hashing is per-process randomized and collides.
    i = _AXIS.get(chunk_id, 3)
    v = [0.01] * DIMS
    v[i] = 1.0
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


@pytest.fixture
def paths(tmp_path):
    arxiv_db = tmp_path / "arxiv.db"
    conn = sqlite3.connect(arxiv_db)
    conn.execute(
        "CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY, title TEXT, authors TEXT,"
        " abstract TEXT, categories TEXT, datestamp TEXT, pdf_path TEXT, fetched_at TEXT,"
        " published TEXT, version TEXT, size_bytes INTEGER, authority REAL, niche_idf REAL,"
        " author_novelty REAL, revisions INTEGER, venue_rigor INTEGER, venue TEXT)"
    )
    for arxiv_id, title, cats, published, version, venue in PAPERS:
        conn.execute(
            "INSERT INTO papers (arxiv_id, title, authors, abstract, categories,"
            " published, version, venue, authority) VALUES (?,?,?,?,?,?,?,?,?)",
            (arxiv_id, title, "A. Author", "An abstract.", cats, published, version, venue, 0.5),
        )
    conn.commit()
    conn.close()

    chunks_jsonl = tmp_path / "chunks.jsonl"
    with chunks_jsonl.open("w") as fh:
        for cid, pid, section, ps, pe, text, n in CHUNKS:
            record = {
                "chunk_id": cid,
                "paper_id": pid,
                "section": section,
                "page_start": ps,
                "page_end": pe,
                "text": text,
                "n_tokens": n,
            }
            fh.write(json.dumps(record) + "\n")

    parquet = tmp_path / f"{SLUG}.parquet"
    write_parquet(parquet, [c[0] for c in CHUNKS])

    text_dir = tmp_path / "text"
    # extract_citations globs this tree, so a paper here is one that reached
    # the reference parser. 2401.00002 is deliberately absent: we hold its
    # metadata and never extracted its text, which is the distinction
    # `papers.has_text` carries and the landing page's parse rate needs.
    (text_dir / "2401").mkdir(parents=True)
    (text_dir / "2401" / "2401.00001.txt").write_text("References: arXiv:1707.06347")

    seed = tmp_path / "archive.zip"
    seed_records = [
        {
            "id": "2401.00001",
            "categories": "cs.CL cs.AI",
            "license": "http://creativecommons.org/licenses/by/4.0/",
            # Seed knows v5, but the row already pins v2 — the build must
            # never let the backfill override a version it already holds.
            "versions": [{"version": "v1"}, {"version": "v5"}],
        },
        {
            "id": "2401.00002",
            "categories": "cs.LG",
            "license": None,  # seed has no license for this one
            "versions": [{"version": "v1"}, {"version": "v2"}, {"version": "v3"}],
        },
        # Catalog rows we do NOT hold: the census counts them (it is arXiv's
        # total for the month, not ours) and skips the non-cs one.
        {"id": "2401.00003", "categories": "cs.CV", "license": None},
        {"id": "2401.00004", "categories": "math.NA cs.CL", "license": None},
        {"id": "9999.99999", "license": "http://example.com/other"},  # not ours
    ]
    with zipfile.ZipFile(seed, "w") as zf:
        zf.writestr(
            "arxiv-metadata-oai-snapshot.json",
            "\n".join(json.dumps(r) for r in seed_records),
        )

    return {
        "arxiv_db": arxiv_db,
        "text": text_dir,
        "chunks": chunks_jsonl,
        "parquet": parquet,
        "seed": seed,
        "corpus_db": tmp_path / "corpus.db",
        "chroma": tmp_path / "chroma",
    }


def write_parquet(path, chunk_ids):
    flat = pa.array([value for cid in chunk_ids for value in vector_for(cid)], type=pa.float32())
    table = pa.table(
        {
            "chunk_id": pa.array(chunk_ids, type=pa.string()),
            "vector": pa.FixedSizeListArray.from_arrays(flat, DIMS),
        }
    ).replace_schema_metadata(PROVENANCE.to_metadata())
    pq.write_table(table, path)


def run(paths, **kwargs):
    # No transport seam: the build is fully offline (D18), so there is no
    # network to mock — versions backfill from the seed snapshot.
    kwargs.setdefault("add_batch_size", 2)  # exercises batching with 3 chunks
    return build_indexes.run(
        arxiv_db=paths["arxiv_db"],
        text_dir=paths["text"],
        chunks_path=paths["chunks"],
        vectors_parquet=paths["parquet"],
        seed_zip=paths["seed"],
        corpus_db=paths["corpus_db"],
        chroma_dir=paths["chroma"],
        collection_name=SLUG,
        **kwargs,
    )


def chroma_client(path):
    # Chroma caches ONE client per path per process and refuses different
    # settings — verification must open with the same settings as the build.
    import chromadb
    import chromadb.config

    return chromadb.PersistentClient(
        path=str(path), settings=chromadb.config.Settings(anonymized_telemetry=False)
    )


# --- the three acceptance checks (issue #14) --------------------------------


def test_chunk_count_matches_chroma_count(paths):
    stats = run(paths)
    conn = sqlite3.connect(paths["corpus_db"])
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 3
    conn.close()
    assert stats.chroma_count == 3 == stats.chunks


def test_fts5_sample_query_returns_the_right_chunk(paths):
    run(paths)
    conn = sqlite3.connect(paths["corpus_db"])
    rows = conn.execute(
        "SELECT c.chunk_id FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
        " WHERE chunks_fts MATCH 'graph' ORDER BY rank"
    ).fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["2401.00002#0"]


def test_vector_sample_query_returns_nearest_chunk(paths):

    run(paths)
    collection = chroma_client(paths["chroma"]).get_collection(SLUG)
    result = collection.query(query_embeddings=[vector_for("2401.00001#1")], n_results=1)
    assert result["ids"] == [["2401.00001#1"]]
    # `where` filter metadata is queryable (D4: paper_id/category/year).
    filtered = collection.query(
        query_embeddings=[vector_for("2401.00001#1")],
        n_results=3,
        where={"paper_id": "2401.00002"},
    )
    assert filtered["ids"] == [["2401.00002#0"]]


def test_versions_and_licenses_land_in_papers(paths):
    stats = run(paths)
    conn = sqlite3.connect(paths["corpus_db"])
    rows = dict(conn.execute("SELECT arxiv_id, version FROM papers").fetchall())
    licenses = dict(conn.execute("SELECT arxiv_id, license FROM papers").fetchall())
    conn.close()
    # 2401.00002's version comes from the seed snapshot (D18), not the network;
    # 2401.00001 already held v2, which the seed's v5 must not override.
    assert rows == {"2401.00001": "v2", "2401.00002": "v3", "0704.0217": "v1"}
    assert stats.versions_backfilled == 1 and stats.versions_missing == 0
    assert licenses["2401.00001"] == "http://creativecommons.org/licenses/by/4.0/"
    assert licenses["2401.00002"] is None  # seed had none — stays NULL, not fabricated


# --- rebuild + failure modes --------------------------------------------------


def test_rebuild_is_idempotent(paths):
    first = run(paths)
    second = run(paths)
    assert (first.papers, first.chunks, first.chroma_count) == (
        second.papers,
        second.chunks,
        second.chroma_count,
    )
    conn = sqlite3.connect(paths["corpus_db"])
    assert conn.execute("SELECT count(*) FROM papers").fetchone()[0] == 3
    conn.close()


def test_backfill_gap_warns_but_builds(paths):
    """An id the snapshot itself lacks keeps a NULL version (D9 fallback)."""
    with zipfile.ZipFile(paths["seed"]) as zf:
        records = [
            json.loads(raw)
            for raw in zf.read("arxiv-metadata-oai-snapshot.json").splitlines()
            if json.loads(raw)["id"] != "2401.00002"
        ]
    with zipfile.ZipFile(paths["seed"], "w") as zf:
        zf.writestr(
            "arxiv-metadata-oai-snapshot.json",
            "\n".join(json.dumps(r) for r in records),
        )
    stats = run(paths)
    assert stats.versions_missing == 1
    conn = sqlite3.connect(paths["corpus_db"])
    version = conn.execute("SELECT version FROM papers WHERE arxiv_id='2401.00002'").fetchone()[0]
    conn.close()
    assert version is None  # D9 fallback: unpinned URL until a later backfill


def test_no_null_versions_means_no_seed_lookup(paths):
    """Rows that already hold versions never consult the snapshot for them."""
    conn = sqlite3.connect(paths["arxiv_db"])
    conn.execute("UPDATE papers SET version='v9' WHERE version IS NULL")
    conn.commit()
    conn.close()
    stats = run(paths)
    assert stats.versions_backfilled == 0
    conn = sqlite3.connect(paths["corpus_db"])
    rows = dict(conn.execute("SELECT arxiv_id, version FROM papers").fetchall())
    conn.close()
    assert rows["2401.00002"] == "v9"


def test_parquet_chunk_missing_from_chunks_fails_loudly(paths):
    write_parquet(paths["parquet"], [c[0] for c in CHUNKS] + ["9999.00000#0"])
    with pytest.raises(IndexBuildError, match="missing from chunks.jsonl"):
        run(paths)
    assert not paths["corpus_db"].exists()  # validation precedes any write


def test_stale_parquet_subset_fails_the_count_invariant(paths):
    write_parquet(paths["parquet"], [CHUNKS[0][0]])  # 1 vector vs 3 chunks
    with pytest.raises(IndexBuildError, match="holds 1 vectors"):
        run(paths)
    assert not paths["corpus_db"].exists()


def test_orphan_chunk_paper_id_fails_before_any_write(paths):
    # Review finding #55-1 (reproduced): a chunk whose paper_id is missing
    # from arxiv.db must fail validation BEFORE corpus.db is replaced —
    # a failed build leaves the previous artifact generation untouched.

    first = run(paths)  # a good previous generation exists on disk
    old_bytes = paths["corpus_db"].read_bytes()

    orphan = {
        "chunk_id": "2401.99999#0",
        "paper_id": "2401.99999",  # not in arxiv.db
        "section": "Intro",
        "page_start": 1,
        "page_end": 1,
        "text": "orphan text",
        "n_tokens": 2,
    }
    with paths["chunks"].open("a") as fh:
        fh.write(json.dumps(orphan) + "\n")
    write_parquet(paths["parquet"], [c[0] for c in CHUNKS] + ["2401.99999#0"])

    with pytest.raises(IndexBuildError, match="missing from arxiv.db"):
        run(paths)

    # Both stores still hold the PREVIOUS generation — no drift.
    assert paths["corpus_db"].read_bytes() == old_bytes
    collection = chroma_client(paths["chroma"]).get_collection(SLUG)
    assert collection.count() == first.chroma_count


def test_corpus_db_foreign_keys_are_enforced_not_decorative(paths, tmp_path):
    # Belt to _validate_inputs' suspenders: the schema's REFERENCES clause
    # actually rejects an orphan row (PRAGMA foreign_keys=ON at build time).
    from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db

    paper = PaperRow(
        arxiv_id="2401.00001",
        title="t",
        authors="a",
        abstract="x",
        categories="cs.CL",
        published="2024-01-02",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )
    orphan_chunk = ChunkRow(
        chunk_id="9999.00000#0",
        paper_id="9999.00000",
        section="s",
        page_start=1,
        page_end=1,
        text="t",
        n_tokens=1,
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _write_corpus_db(tmp_path / "corpus.db", [paper], [orphan_chunk])


def test_other_models_parquet_is_refused(paths):
    # The per-model keying contract from #13, enforced at the read side:
    # a parquet whose provenance names another model never loads into this
    # model's collection.
    from dataclasses import replace

    from askrag.ingest.embed_chunks import EmbeddingError

    other = replace(PROVENANCE, slug="other-model_4", model="fake/other-model")
    flat = pa.array([value for c in CHUNKS for value in vector_for(c[0])], type=pa.float32())
    table = pa.table(
        {
            "chunk_id": pa.array([c[0] for c in CHUNKS], type=pa.string()),
            "vector": pa.FixedSizeListArray.from_arrays(flat, DIMS),
        }
    ).replace_schema_metadata(other.to_metadata())
    pq.write_table(table, paths["parquet"])
    with pytest.raises(EmbeddingError, match=f"expected '{SLUG}'"):
        run(paths)


# --- the citation graph (landing page) --------------------------------------


def _citation_inputs(tmp_path, edges, works):
    """Write the two optional citation inputs; return their paths."""
    citations = tmp_path / "citations.tsv"
    citations.write_text("".join(f"{a}\t{b}\n" for a, b in edges), encoding="utf-8")
    cited_works = tmp_path / "cited_works.jsonl"
    cited_works.write_text(
        "".join(json.dumps(w) + "\n" for w in works),
        encoding="utf-8",
    )
    return {"citations_path": citations, "cited_works_path": cited_works}


def _work(arxiv_id, title="A cited work"):
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": "A. Author",
        "primary_category": "cs.LG",
        "year": 2017,
        "version": "v2",
    }


def test_the_catalog_census_and_text_flags_land_in_corpus_db(paths):
    """The denominator and the parse-rate numerator, both absent before.

    Without `catalog_months` the landing page had no way to say what share of
    a month it holds, so it claimed "every cs paper arXiv posted" (measured
    94% / 49% / 5% for July, August and September 2026). Without `has_text`
    it divided by every catalog row and reported a 30% parse rate for a
    parser that yields 81%.
    """
    stats = run(paths)

    assert stats.papers_with_text == 1
    assert stats.catalog_months == 1
    conn = sqlite3.connect(paths["corpus_db"])
    try:
        # 3 cs-primary catalog rows for 2401; the math.NA-primary one is not
        # counted, matching how the collector selected papers. We hold 2.
        assert conn.execute("SELECT * FROM catalog_months").fetchall() == [("2401", 3)]
        assert conn.execute(
            "SELECT arxiv_id, has_text FROM papers WHERE arxiv_id LIKE '2401.%' ORDER BY arxiv_id"
        ).fetchall() == [("2401.00001", 1), ("2401.00002", 0)]
    finally:
        conn.close()


def test_citations_and_cited_works_land_in_corpus_db(paths, tmp_path):
    inputs = _citation_inputs(
        tmp_path,
        [("2401.00001", "1707.06347"), ("2401.00002", "1707.06347")],
        [_work("1707.06347", "Proximal Policy Optimization Algorithms")],
    )

    stats = run(paths, **inputs)

    assert (stats.citations, stats.cited_works) == (2, 1)
    conn = sqlite3.connect(paths["corpus_db"])
    try:
        assert conn.execute("SELECT count(*) FROM citations").fetchone()[0] == 2
        # The landing page's core query: who cites this, and what is it called?
        row = conn.execute(
            "SELECT w.title, count(*) FROM citations c"
            " JOIN cited_works w ON w.arxiv_id = c.cited_id"
            " GROUP BY c.cited_id"
        ).fetchone()
        assert row == ("Proximal Policy Optimization Algorithms", 2)
    finally:
        conn.close()


def test_a_cited_work_we_never_hold_is_not_a_paper(paths, tmp_path):
    """The D16 boundary in the schema: cited_works is not a second papers table.

    1707.06347 is cited but absent from `papers`, so nothing that scopes to the
    indexed corpus can ever surface it as retrievable.
    """
    inputs = _citation_inputs(tmp_path, [("2401.00001", "1707.06347")], [_work("1707.06347")])

    run(paths, **inputs)

    conn = sqlite3.connect(paths["corpus_db"])
    try:
        assert (
            conn.execute("SELECT count(*) FROM papers WHERE arxiv_id = '1707.06347'").fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM cited_works WHERE arxiv_id = '1707.06347'"
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_build_without_citation_inputs_still_succeeds(paths):
    """A corpus built before extract_citations ran is a valid artifact."""
    stats = run(paths)

    assert (stats.citations, stats.cited_works) == (0, 0)
    conn = sqlite3.connect(paths["corpus_db"])
    try:
        assert conn.execute("SELECT count(*) FROM citations").fetchone()[0] == 0
    finally:
        conn.close()


def test_citation_from_an_unknown_paper_fails_before_any_write(paths, tmp_path):
    inputs = _citation_inputs(tmp_path, [("2499.99999", "1707.06347")], [_work("1707.06347")])

    with pytest.raises(IndexBuildError, match="missing in arxiv.db"):
        run(paths, **inputs)

    assert not paths["corpus_db"].exists()


def test_stale_cited_works_fails_before_any_write(paths, tmp_path):
    """citations.tsv regenerated without rerunning resolve_cited_works."""
    inputs = _citation_inputs(tmp_path, [("2401.00001", "1707.06347")], [])

    with pytest.raises(IndexBuildError, match="rerun resolve_cited_works"):
        run(paths, **inputs)

    assert not paths["corpus_db"].exists()


def test_the_build_leaves_planner_stats_behind(tmp_path):
    """ANALYZE at build time is worth 17% on the cited-year histogram.

    Measured 2026-08-28 over 162k edges: 110 ms without stats, 91 ms with.
    The snapshot is frozen (D12), so stats written once stay accurate.
    """
    from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db

    paper = PaperRow(
        arxiv_id="2608.00001",
        title="A paper",
        authors="A. Author",
        abstract="An abstract.",
        categories="cs.CL",
        published="2026-08-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )
    chunk = ChunkRow("2608.00001#0", "2608.00001", "__paper__", 1, 1, "some text", 2)

    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, [paper], [chunk])
    conn = sqlite3.connect(f"file:{corpus_db}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()

    assert "sqlite_stat1" in tables
    # The (arxiv_id, year) covering index was measured to buy nothing; if it
    # comes back, it needs a measurement, not an intuition.
    assert "cited_works_year" not in indexes


def test_a_metadata_only_build_writes_corpus_db_and_leaves_the_vector_store_alone(paths):
    """corpus.db and the vector store age at different speeds.

    A month of new papers reaches the page's numbers in minutes and the
    embedder in hours (measured 2026-09-16: ~1,000 chunks/hour on this box),
    so a metadata-only rebuild ships the first without waiting for the
    second. What it must never do is pretend the two agree.
    """
    run(paths)  # a full build first, so there is a chroma generation to leave alone
    write_parquet(paths["parquet"], [c[0] for c in CHUNKS[:2]])  # the third chunk loses its vector

    stats = run(paths, without_vectors=True)

    conn = sqlite3.connect(paths["corpus_db"])
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 3
    conn.close()
    assert stats.chunks_without_vectors == 1
    # Untouched, not rebuilt short: the previous generation still answers.
    collection = chroma_client(paths["chroma"]).get_collection(SLUG)
    assert collection.count() == 3
    assert stats.chroma_count == 0


def test_a_full_build_still_refuses_a_chunk_without_a_vector(paths):
    write_parquet(paths["parquet"], [c[0] for c in CHUNKS[:2]])

    with pytest.raises(build_indexes.IndexBuildError, match="re-run embed_chunks"):
        run(paths)


def test_the_thumbnail_manifest_reaches_the_papers_table(paths, tmp_path):
    """render_thumbnails and the build are separate stages, joined only by the
    manifest: a paper listed there gets its path on the row, and a paper that
    is not (no PDF, or a licence that forbids the crop) stays NULL rather than
    getting a path that would 404."""
    manifest = tmp_path / "thumbnails.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "arxiv_id": "2401.00001",
                "path": "2024/01/2401.00001.jpg",
                "source": "figure",
                "width": 320,
                "height": 200,
            }
        )
        + "\n"
    )

    run(paths, thumbnails_path=manifest)

    conn = sqlite3.connect(paths["corpus_db"])
    thumbnails = dict(conn.execute("SELECT arxiv_id, thumbnail FROM papers"))
    conn.close()
    assert thumbnails["2401.00001"] == "2024/01/2401.00001.jpg"
    assert thumbnails["2401.00002"] is None


def test_a_build_with_no_manifest_is_a_build_with_no_thumbnails(paths):
    """Rendering is optional: `just index-metadata` on a box that has never
    run `just thumbnails` must produce a corpus, not an error."""
    stats = run(paths)

    conn = sqlite3.connect(paths["corpus_db"])
    assert (
        conn.execute("SELECT count(*) FROM papers WHERE thumbnail IS NOT NULL").fetchone()[0] == 0
    )
    conn.close()
    assert stats.thumbnails_found == 0
