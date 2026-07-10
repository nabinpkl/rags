"""Tests for askrag.api.routes_explorer — GET /api/papers, /api/papers/{id},
/api/facets (issue #27). §6c rows (no chunk text on the list/search paths;
the capped ?chunks= lookup is the only route chunks.text reaches the wire
through) are test-first per the issue's own instruction."""

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag.api import routes_explorer
from askrag.config import Settings, get_settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.retrieval.hybrid_search import ScoredChunk


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
# #73) — pagination/sort/facets tests below exercise mechanics unrelated to
# indexed-scoping, which gets its own dedicated fixture further down.
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


class FakeSearcher:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls: list[dict] = []

    def search(self, query, filters=None, k=None):
        self.calls.append({"query": query, "filters": filters, "k": k})
        return self._chunks


def make_settings(tmp_path, corpus_db, **overrides):
    return Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=corpus_db.parent,
        _env_file=None,  # ty: ignore[unknown-argument]
        **overrides,
    )


def make_app(*, settings, searcher=None) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_explorer.router)
    app.dependency_overrides[get_settings] = lambda: settings
    if searcher is not None:
        app.dependency_overrides[routes_explorer.get_hybrid_search_factory] = lambda: (
            lambda: searcher
        )
    return app


# --- §6c, test-first: no chunk text on the list/search paths ---------------


def test_chunks_text_column_is_selected_only_by_the_capped_excerpt_lookup():
    # Grep-verifiable per the issue: chunks.text reaches the wire only via
    # the capped GET /api/papers/{id}?chunks= path. get_paper's own
    # `SELECT COUNT(*) FROM chunks` (n_chunks) is fine — it never selects
    # the `text` column, only counts rows.
    source = inspect.getsource(routes_explorer)
    text_selecting_queries = [
        line for line in source.splitlines() if "FROM chunks" in line and "text" in line
    ]
    assert len(text_selecting_queries) == 1
    excerpts_fn = inspect.getsource(routes_explorer._cited_excerpts)
    assert text_selecting_queries[0].strip() in excerpts_fn


def test_papers_list_rows_carry_no_chunk_or_text_field(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"]
    for item in body["items"]:
        assert set(item.keys()) == {
            "arxiv_id",
            "title",
            "authors",
            "abstract",
            "primary_category",
            "year",
            "venue",
            "license",
            "version",
            "score",
            "facets",
        }


# --- GET /api/papers — metadata-only browse (q empty): keyset pagination ---


def test_browse_default_sort_is_year_desc_with_arxiv_id_tiebreak(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers")
    ids = [i["arxiv_id"] for i in resp.json()["items"]]
    # years: 2024, 2023, 2023, 2022, 2024 -> desc by year, arxiv_id asc within a year
    assert ids == ["2401.00001", "2401.00005", "2401.00002", "2401.00003", "2401.00004"]


def test_browse_total_populated_on_first_page_only(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=2)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        first = tc.get("/api/papers").json()
        assert first["total"] == 5
        cursor = first["next_cursor"]
        assert cursor
        second = tc.get("/api/papers", params={"cursor": cursor}).json()
        assert second["total"] is None


def test_keyset_cursor_walks_every_paper_exactly_once(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=2)
    app = make_app(settings=settings)
    seen: list[str] = []
    with TestClient(app) as tc:
        cursor = None
        for _ in range(10):  # bounded loop; 5 papers / page_size 2 -> 3 pages
            params = {"cursor": cursor} if cursor else {}
            body = tc.get("/api/papers", params=params).json()
            seen.extend(i["arxiv_id"] for i in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
    assert sorted(seen) == sorted(p.arxiv_id for p in PAPERS)
    assert len(seen) == len(set(seen))  # no duplicate across pages


def test_browse_filters_bind_category_and_year(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"category": "cs.CL", "year_from": 2023})
    ids = {i["arxiv_id"] for i in resp.json()["items"]}
    assert ids == {"2401.00001", "2401.00002"}


def test_browse_sort_year_asc(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"sort": "year_asc"})
    ids = [i["arxiv_id"] for i in resp.json()["items"]]
    assert ids == ["2401.00004", "2401.00002", "2401.00003", "2401.00001", "2401.00005"]


def test_browse_sort_title_asc(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"sort": "title_asc"})
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == sorted(titles)


def test_cursor_rejected_when_filters_change(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=2)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        first = tc.get("/api/papers").json()
        cursor = first["next_cursor"]
        resp = tc.get("/api/papers", params={"cursor": cursor, "category": "cs.CL"})
    assert resp.status_code == 400


def test_invalid_cursor_is_400(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"cursor": "not-a-real-cursor"})
    assert resp.status_code == 400


def test_sort_relevance_without_q_is_400(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"sort": "relevance"})
    assert resp.status_code == 400


# --- GET /api/papers — facets= (diversity-score columns) -------------------


def test_facets_param_includes_requested_diversity_scores(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"facets": "authority"})
    by_id = {i["arxiv_id"]: i for i in resp.json()["items"]}
    assert by_id["2401.00001"]["facets"] == {"authority": 0.9}
    assert by_id["2401.00002"]["facets"] == {"authority": None}


def test_facets_param_rejects_unknown_name(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"facets": "bogus_facet"})
    assert resp.status_code == 400


# --- GET /api/papers — semantic path: collapse chunks -> papers ------------


def test_semantic_search_collapses_chunks_to_distinct_papers_preserving_best_rank(
    tmp_path, corpus_db
):
    # Fused-score order (as HybridSearch.search() already returns): two hits
    # on paper 1 (best first) and one on paper 2 further down.
    chunks = [
        ScoredChunk(
            chunk_id="2401.00001#0",
            paper_id="2401.00001",
            section="Intro",
            page_start=1,
            page_end=1,
            text=_LONG_TEXT,
            score=0.9,
            leg="both",
            version="v1",
        ),
        ScoredChunk(
            chunk_id="2401.00001#1",
            paper_id="2401.00001",
            section="Method",
            page_start=2,
            page_end=2,
            text="short method text",
            score=0.5,
            leg="bm25",
            version="v1",
        ),
        ScoredChunk(
            chunk_id="2401.00002#0",
            paper_id="2401.00002",
            section="__paper__",
            page_start=1,
            page_end=1,
            text="graph algorithms text",
            score=0.4,
            leg="vector",
            version="v1",
        ),
    ]
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=10)
    app = make_app(settings=settings, searcher=FakeSearcher(chunks))
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"q": "attention"})
    items = resp.json()["items"]
    assert [i["arxiv_id"] for i in items] == ["2401.00001", "2401.00002"]
    assert items[0]["score"] == pytest.approx(0.9)  # best of the two paper-1 hits, first-seen
    assert items[1]["score"] == pytest.approx(0.4)
    assert resp.json()["total"] is None
    # No chunk text leaked onto the response row (§6c) even though the fake
    # searcher's ScoredChunks carried real chunk text internally.
    for item in items:
        assert "text" not in item


def test_semantic_search_pushes_filters_and_k_into_hybrid_search(tmp_path, corpus_db):
    searcher = FakeSearcher([])
    settings = make_settings(tmp_path, corpus_db, explorer_search_k=42)
    app = make_app(settings=settings, searcher=searcher)
    with TestClient(app) as tc:
        tc.get(
            "/api/papers",
            params={"q": "cot", "category": "cs.CL", "year_from": 2023, "year_to": 2024},
        )
    assert len(searcher.calls) == 1
    call = searcher.calls[0]
    assert call["query"] == "cot"
    assert call["k"] == 42
    assert call["filters"].category == "cs.CL"
    assert call["filters"].year_min == 2023
    assert call["filters"].year_max == 2024


def test_semantic_search_bounded_list_paginates_via_cursor(tmp_path, corpus_db):
    chunks = [
        ScoredChunk(
            chunk_id=f"2401.0000{i}#0",
            paper_id=f"2401.0000{i}",
            section="s",
            page_start=1,
            page_end=1,
            text="t",
            score=1.0 - i * 0.1,
            leg="both",
            version="v1",
        )
        for i in range(1, 6)
    ]
    settings = make_settings(tmp_path, corpus_db, explorer_page_size=2)
    app = make_app(settings=settings, searcher=FakeSearcher(chunks))
    seen: list[str] = []
    with TestClient(app) as tc:
        cursor = None
        for _ in range(10):
            params = {"q": "x"}
            if cursor:
                params["cursor"] = cursor
            body = tc.get("/api/papers", params=params).json()
            seen.extend(i["arxiv_id"] for i in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
    assert seen == [f"2401.0000{i}" for i in range(1, 6)]


# --- GET /api/papers/{id} ----------------------------------------------------


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


# --- GET /api/facets ----------------------------------------------------------


def test_facets_endpoint_counts_all_four_dimensions(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/facets")
    body = resp.json()
    assert body["total"] == 5
    assert {(b["value"], b["count"]) for b in body["category"]["buckets"]} == {
        ("cs.CL", 3),
        ("cs.LG", 1),
        ("cs.CV", 1),
    }
    assert body["category"]["truncated"] is False
    assert {(b["value"], b["count"]) for b in body["year"]["buckets"]} == {
        (2024, 2),
        (2023, 2),
        (2022, 1),
    }


def test_facets_endpoint_scoped_by_category_and_year(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/facets", params={"category": "cs.CL"})
    body = resp.json()
    assert body["total"] == 3
    assert {(b["value"], b["count"]) for b in body["category"]["buckets"]} == {("cs.CL", 3)}


def test_facets_endpoint_flags_truncation_per_dimension(tmp_path, corpus_db):
    settings = make_settings(tmp_path, corpus_db, explorer_facets_max_groups=1)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/facets")
    body = resp.json()
    assert len(body["category"]["buckets"]) == 1
    assert body["category"]["truncated"] is True


# --- indexed-corpus scoping (D16, issue #73): the API exposes only papers --
# --- with chunks; a chunk-less paper is invisible everywhere except the ----
# --- underlying `papers` row (which the explorer routes never expose raw). -


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


def test_browse_returns_only_indexed_papers(tmp_path, scoped_corpus_db):
    settings = make_settings(tmp_path, scoped_corpus_db, explorer_page_size=10)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/papers")
    body = resp.json()
    ids = {i["arxiv_id"] for i in body["items"]}
    assert ids == {"2401.10001", "2401.10002"}
    assert body["total"] == 2  # not 3 — the chunk-less paper doesn't count


def test_facets_endpoint_scopes_total_and_buckets_to_indexed(tmp_path, scoped_corpus_db):
    settings = make_settings(tmp_path, scoped_corpus_db)
    app = make_app(settings=settings)
    with TestClient(app) as tc:
        resp = tc.get("/api/facets")
    body = resp.json()
    assert body["total"] == 2
    # cs.LG (2401.10003, chunk-less) never appears as a bucket.
    assert {(b["value"], b["count"]) for b in body["category"]["buckets"]} == {("cs.CL", 2)}


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


def test_semantic_search_is_unaffected_by_indexed_scoping(tmp_path, scoped_corpus_db):
    # Search hydrates rows from ids HybridSearch returns, which only ever
    # come from `chunks` — already indexed-only by construction. Confirmed
    # here, not re-scoped: a fake searcher "finding" a chunk-less paper's id
    # is a searcher bug, not something routes_explorer should guard against.
    chunks = [
        ScoredChunk(
            chunk_id="2401.10001#0",
            paper_id="2401.10001",
            section="__paper__",
            page_start=1,
            page_end=1,
            text="indexed a text",
            score=0.9,
            leg="both",
            version="v1",
        )
    ]
    settings = make_settings(tmp_path, scoped_corpus_db, explorer_page_size=10)
    app = make_app(settings=settings, searcher=FakeSearcher(chunks))
    with TestClient(app) as tc:
        resp = tc.get("/api/papers", params={"q": "indexed"})
    ids = {i["arxiv_id"] for i in resp.json()["items"]}
    assert ids == {"2401.10001"}
