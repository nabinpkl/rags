"""Tests for askrag.api.routes_paper_detail — GET /api/papers/{id}, the
reader's record for one indexed paper. §6c row 4 (the capped ?chunks= lookup
is the only route chunks.text reaches the wire through) is test-first."""

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag.api import routes_paper_detail
from askrag.config import Settings, get_settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db


def paper(
    arxiv_id,
    *,
    title=None,
    year=2024,
    category="cs.CL",
    license=None,
    venue=None,
    authority=None,
    niche_idf=None,
    author_novelty=None,
    revisions=None,
    venue_rigor=None,
):
    return PaperRow(
        arxiv_id=arxiv_id,
        title=title or f"title-{arxiv_id}",
        authors="A. Author",
        abstract=f"abstract-{arxiv_id}",
        categories=category,
        published=f"{year}-01-01",
        version="v1",
        license=license,
        venue=venue,
        authority=authority,
        niche_idf=niche_idf,
        author_novelty=author_novelty,
        revisions=revisions,
        venue_rigor=venue_rigor,
    )


PAPERS = [
    paper(
        "2401.00001",
        title="Attention is enough",
        year=2024,
        category="cs.CL",
        license="CC-BY-4.0",
        venue="ACL",
        authority=0.9,
    ),
    paper("2401.00002", title="Graphs at scale", year=2023, category="cs.CL"),
    paper(
        "2401.00003",
        title="Fading channels",
        year=2023,
        category="cs.LG",
        license="CC-BY-4.0",
        venue="NeurIPS",
    ),
    paper("2401.00004", title="Zero shot learning", year=2022, category="cs.CL"),
    paper("2401.00005", title="Diffusion models", year=2024, category="cs.CV"),
]

# 4 chunks on paper 1: one long enough to exercise the 50-word cap, plus
# enough distinct chunks to exercise the 3-quote cap. Every PAPERS row gets
# at least one chunk so this base fixture is entirely indexed (D16, issue
# #73); indexed-scoping gets its own fixture further down.
_LONG_TEXT = " ".join(f"word{i}" for i in range(1, 61))  # 60 words > quote_max_words=50
CHUNKS = [
    ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, _LONG_TEXT, 60),
    ChunkRow("2401.00001#1", "2401.00001", "Method", 2, 2, "short method text", 3),
    ChunkRow("2401.00001#2", "2401.00001", "Results", 3, 3, "short results text", 3),
    ChunkRow("2401.00001#3", "2401.00001", "Conclusion", 4, 4, "short conclusion text", 3),
    ChunkRow("2401.00002#0", "2401.00002", "__paper__", 1, 1, "graph algorithms text", 3),
    ChunkRow("2401.00003#0", "2401.00003", "__paper__", 1, 1, "fading channels text", 3),
    ChunkRow("2401.00004#0", "2401.00004", "__paper__", 1, 1, "zero shot text", 3),
    ChunkRow("2401.00005#0", "2401.00005", "__paper__", 1, 1, "diffusion text", 3),
]


@pytest.fixture
def corpus_db(tmp_path):
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, PAPERS, CHUNKS)
    return path


def make_settings(tmp_path, corpus_db, **overrides):
    return Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=corpus_db.parent,
        _env_file=None,  # ty: ignore[unknown-argument]
        **overrides,
    )


def make_app(*, settings) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_paper_detail.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


# --- §6c, test-first: chunk text only through the capped lookup -----------


def test_chunks_text_column_is_selected_only_by_the_capped_excerpt_lookup():
    # chunks.text reaches the wire only via the capped ?chunks= path.
    # get_paper's own `SELECT COUNT(*) FROM chunks` (n_chunks) never selects
    # the `text` column, only counts rows.
    source = inspect.getsource(routes_paper_detail)
    text_selecting_queries = [
        line for line in source.splitlines() if "FROM chunks" in line and "text" in line
    ]
    assert len(text_selecting_queries) == 1
    excerpts_fn = inspect.getsource(routes_paper_detail._cited_excerpts)
    assert text_selecting_queries[0].strip() in excerpts_fn


# --- GET /api/papers/{id} ---------------------------------------------------


def test_get_paper_detail_includes_facets_and_version(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.00001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Attention is enough"
    assert body["version"] == "v1"
    assert body["facets"]["authority"] == 0.9
    assert body["n_chunks"] == 4
    assert body["excerpts"] == []
    assert body["excerpts_truncated"] is False


def test_get_paper_detail_404_for_unknown_id(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/9999.99999")
    assert resp.status_code == 404


# --- §6c row 4, test-first: cited-excerpt cap enforcement -------------------


def test_cited_excerpts_capped_at_max_quotes_per_paper(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, max_quotes_per_paper=3)
    app = make_app(settings=settings)
    requested = "2401.00001#0,2401.00001#1,2401.00001#2,2401.00001#3"
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.00001", params={"chunks": requested})
    body = resp.json()
    assert len(body["excerpts"]) == 3
    assert body["excerpts_truncated"] is True
    assert [e["chunk_id"] for e in body["excerpts"]] == [
        "2401.00001#0",
        "2401.00001#1",
        "2401.00001#2",
    ]


def test_cited_excerpt_text_capped_at_quote_max_words(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, quote_max_words=50)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.00001", params={"chunks": "2401.00001#0"})
    text = resp.json()["excerpts"][0]["text"]
    assert len(text.split()) == 50
    assert text == " ".join(f"word{i}" for i in range(1, 51))


def test_cited_excerpts_not_truncated_when_within_cap(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, max_quotes_per_paper=3)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.00001", params={"chunks": "2401.00001#1,2401.00001#2"})
    body = resp.json()
    assert len(body["excerpts"]) == 2
    assert body["excerpts_truncated"] is False


def test_cited_excerpts_only_return_chunks_belonging_to_the_requested_paper(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        # chunk 2401.00002#0 belongs to a DIFFERENT paper than the one in the path.
        resp = tc.get("/api/papers/2401.00001", params={"chunks": "2401.00001#0,2401.00002#0"})
    ids = [e["chunk_id"] for e in resp.json()["excerpts"]]
    assert ids == ["2401.00001#0"]


# --- indexed-corpus scoping (D16, issue #73): a chunk-less paper is -------
# --- indistinguishable from an unknown one. --------------------------------


SCOPED_PAPERS = [
    paper("2401.10001", title="Indexed A", year=2024, category="cs.CL"),
    paper("2401.10002", title="Indexed B", year=2023, category="cs.CL"),
    # No chunks below: exists in `papers`, never indexed.
    paper("2401.10003", title="Not indexed", year=2023, category="cs.LG"),
]
SCOPED_CHUNKS = [
    ChunkRow("2401.10001#0", "2401.10001", "__paper__", 1, 1, "indexed a text", 3),
    ChunkRow("2401.10002#0", "2401.10002", "__paper__", 1, 1, "indexed b text", 3),
]


@pytest.fixture
def scoped_corpus_db(tmp_path):
    scoped_dir = tmp_path / "scoped"
    scoped_dir.mkdir()
    path = scoped_dir / "corpus.db"
    _write_corpus_db(path, SCOPED_PAPERS, SCOPED_CHUNKS)
    return path


def test_get_paper_detail_404s_for_a_chunkless_paper(tmp_path, scoped_corpus_db):
    settings = make_settings(tmp_path, scoped_corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.10003")
    assert resp.status_code == 404


def test_get_paper_detail_200s_for_an_indexed_paper(tmp_path, scoped_corpus_db):
    settings = make_settings(tmp_path, scoped_corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers/2401.10001")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Indexed A"
