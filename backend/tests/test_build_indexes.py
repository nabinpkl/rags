"""Tests for askrag.ingest.build_indexes — corpus.db + per-model chroma."""

import json
import sqlite3
import zipfile

import httpx
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

    seed = tmp_path / "archive.zip"
    seed_records = [
        {"id": "2401.00001", "license": "http://creativecommons.org/licenses/by/4.0/"},
        {"id": "2401.00002", "license": None},  # seed has no license for this one
        {"id": "9999.99999", "license": "http://example.com/other"},  # not ours
    ]
    with zipfile.ZipFile(seed, "w") as zf:
        zf.writestr(
            "arxiv-metadata-oai-snapshot.json",
            "\n".join(json.dumps(r) for r in seed_records),
        )

    return {
        "arxiv_db": arxiv_db,
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


ATOM_OK = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2401.00002v3</id></entry>
</feed>"""


def atom_transport(requests, body=ATOM_OK):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


def chroma_client(path):
    # Chroma caches ONE client per path per process and refuses different
    # settings — verification must open with the same settings as the build.
    import chromadb
    import chromadb.config

    return chromadb.PersistentClient(
        path=str(path), settings=chromadb.config.Settings(anonymized_telemetry=False)
    )


def run(paths, transport=None, **kwargs):
    requests: list[httpx.Request] = []
    kwargs.setdefault("add_batch_size", 2)  # exercises batching with 3 chunks
    kwargs.setdefault("backfill_timeout_seconds", 5.0)
    stats = build_indexes.run(
        arxiv_db=paths["arxiv_db"],
        chunks_path=paths["chunks"],
        vectors_parquet=paths["parquet"],
        seed_zip=paths["seed"],
        corpus_db=paths["corpus_db"],
        chroma_dir=paths["chroma"],
        collection_name=SLUG,
        backfill_transport=transport if transport is not None else atom_transport(requests),
        **kwargs,
    )
    return stats, requests


# --- the three acceptance checks (issue #14) --------------------------------


def test_chunk_count_matches_chroma_count(paths):
    stats, _ = run(paths)
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
    stats, requests = run(paths)
    conn = sqlite3.connect(paths["corpus_db"])
    rows = dict(conn.execute("SELECT arxiv_id, version FROM papers").fetchall())
    licenses = dict(conn.execute("SELECT arxiv_id, license FROM papers").fetchall())
    conn.close()
    assert rows == {"2401.00001": "v2", "2401.00002": "v3", "0704.0217": "v1"}
    assert stats.versions_backfilled == 1 and stats.versions_missing == 0
    assert licenses["2401.00001"] == "http://creativecommons.org/licenses/by/4.0/"
    assert licenses["2401.00002"] is None  # seed had none — stays NULL, not fabricated
    # ONE batched call (D9): all NULL-version ids in a single id_list.
    assert len(requests) == 1
    assert requests[0].url.params["id_list"] == "2401.00002"


# --- rebuild + failure modes --------------------------------------------------


def test_rebuild_is_idempotent(paths):
    first, _ = run(paths)
    second, _ = run(paths)
    assert (first.papers, first.chunks, first.chroma_count) == (
        second.papers,
        second.chunks,
        second.chroma_count,
    )
    conn = sqlite3.connect(paths["corpus_db"])
    assert conn.execute("SELECT count(*) FROM papers").fetchone()[0] == 3
    conn.close()


def test_backfill_gap_warns_but_builds(paths):
    empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    requests: list[httpx.Request] = []
    stats, _ = run(paths, transport=atom_transport(requests, body=empty_feed))
    assert stats.versions_missing == 1
    conn = sqlite3.connect(paths["corpus_db"])
    version = conn.execute("SELECT version FROM papers WHERE arxiv_id='2401.00002'").fetchone()[0]
    conn.close()
    assert version is None  # D9 fallback: unpinned URL until a later backfill


def test_no_null_versions_means_no_network_call(paths):
    conn = sqlite3.connect(paths["arxiv_db"])
    conn.execute("UPDATE papers SET version='v1' WHERE version IS NULL")
    conn.commit()
    conn.close()

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no backfill call expected")

    stats, _ = run(paths, transport=httpx.MockTransport(explode))
    assert stats.versions_backfilled == 0


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

    first, _ = run(paths)  # a good previous generation exists on disk
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


def test_dtd_in_backfill_response_is_refused(paths):
    dtd = '<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "b">]><feed/>'
    requests: list[httpx.Request] = []
    with pytest.raises(IndexBuildError, match="DTD"):
        run(paths, transport=atom_transport(requests, body=dtd))
