"""routes_catalog: the one list surface that shows papers we cannot retrieve."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag.api import routes_catalog
from askrag.config import Settings, get_settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.ingest.resolve_cited_works import CitedWorkRow


def _paper(
    arxiv_id: str,
    title: str,
    abstract: str = "An abstract about nothing in particular.",
    category: str = "cs.CL",
    has_text: bool = True,
    license: str | None = None,
) -> PaperRow:
    return PaperRow(
        arxiv_id=arxiv_id,
        title=title,
        authors="A. Author, B. Author, C. Author",
        abstract=abstract,
        categories=category,
        published=f"20{arxiv_id[:2]}-0{arxiv_id[2]}-0{arxiv_id[3]}",
        version="v1",
        license=license,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
        has_text=has_text,
    )


# One indexed paper, one with text but no chunks, one the catalog knows and
# nothing else. Only the first can reach the reader; all three must be listed.
PAPERS = [
    _paper(
        "2607.00001",
        "Diffusion models for video",
        "We train a diffusion model.",
        "cs.CV",
        license="http://creativecommons.org/licenses/by/4.0/",
    ),
    _paper("2608.00002", "Retrieval augmented generation", "Retrieval helps.", "cs.CL"),
    _paper("2608.00003", "A paper with no text at all", "Nothing extracted.", "cs.CL", False),
]
CHUNKS = [ChunkRow("2607.00001#0", "2607.00001", "__paper__", 1, 1, "diffusion", 3)]
CITED_WORKS = [CitedWorkRow("2607.00001", "Diffusion models for video", "A.", "cs.CV", 2026, "v1")]
CITATIONS = [("2608.00002", "2607.00001"), ("2608.00003", "2607.00001")]
CATALOG_MONTHS = {"2607": 1, "2608": 2}


def _client(tmp_path, **overrides) -> TestClient:
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
        **overrides,
    )
    app = FastAPI()
    app.include_router(routes_catalog.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    _write_corpus_db(tmp_path / "corpus.db", PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)
    return _client(tmp_path)


def test_the_catalog_lists_papers_no_other_surface_will_show(client):
    """D16's amendment in one assertion: /api/papers hides a chunk-less paper
    because it promises retrieval. This route promises only what the catalog
    knows, so all three rows appear and each says what we hold of it."""
    body = client.get("/api/catalog/papers").json()

    assert body["total"] == 3
    held = {paper["arxiv_id"]: (paper["has_text"], paper["indexed"]) for paper in body["papers"]}
    assert held == {
        "2607.00001": (True, True),
        "2608.00002": (True, False),
        "2608.00003": (False, False),
    }


def test_holding_narrows_to_what_we_actually_have(client):
    indexed = client.get("/api/catalog/papers?holding=indexed").json()
    with_text = client.get("/api/catalog/papers?holding=text").json()

    assert [paper["arxiv_id"] for paper in indexed["papers"]] == ["2607.00001"]
    assert sorted(paper["arxiv_id"] for paper in with_text["papers"]) == [
        "2607.00001",
        "2608.00002",
    ]


def test_the_query_searches_titles_and_abstracts_by_word(client):
    """The abstract is the point: it exists for every catalog row, so the
    filter reaches papers whose PDF was never fetched."""
    by_title = client.get("/api/catalog/papers?q=retrieval&sort=relevance").json()
    by_abstract = client.get("/api/catalog/papers?q=extracted&sort=relevance").json()

    assert [paper["arxiv_id"] for paper in by_title["papers"]] == ["2608.00002"]
    assert [paper["arxiv_id"] for paper in by_abstract["papers"]] == ["2608.00003"]
    assert by_abstract["papers"][0]["indexed"] is False


def test_a_half_typed_query_filters_instead_of_raising(client):
    """fts5 reads its input as a query language, so `"chain of` or a trailing
    AND is a syntax error mid-keystroke rather than a search for those words."""
    for raw in ('"unbalanced', "diffusion AND", "AND OR NOT", "*", "  "):
        response = client.get("/api/catalog/papers", params={"q": raw})
        assert response.status_code == 200, raw


def test_an_empty_query_filters_nothing_rather_than_everything(client):
    """A box holding only punctuation has no words in it, which is not the
    same as a filter that matches nothing."""
    assert client.get("/api/catalog/papers", params={"q": "***"}).json()["total"] == 3


def test_relevance_without_a_query_is_refused_rather_than_silently_reordered(client):
    assert client.get("/api/catalog/papers?sort=relevance").status_code == 422


def test_a_month_that_is_not_an_id_month_is_refused(client):
    assert client.get("/api/catalog/papers?month=2026-08").status_code == 422
    assert client.get("/api/catalog/papers?month=2608").json()["total"] == 2


def test_cited_by_counts_citations_from_the_papers_we_parsed(client):
    body = client.get("/api/catalog/papers?sort=cited").json()

    assert body["papers"][0]["arxiv_id"] == "2607.00001"
    assert body["papers"][0]["cited_by"] == 2
    assert body["papers"][-1]["cited_by"] == 0


def test_a_facet_drops_its_own_filter_so_the_counts_answer_what_if(client):
    """Counting cs.CL under a cs.CL filter would report the filter back at the
    reader; the useful number is what the other choice holds."""
    body = client.get("/api/catalog/facets?category=cs.CV").json()

    assert {bucket["value"]: bucket["papers"] for bucket in body["categories"]} == {
        "cs.CV": 1,
        "cs.CL": 2,
    }
    # The month facet keeps the category filter, because only its own is dropped.
    assert {bucket["value"]: bucket["papers"] for bucket in body["months"]} == {"2607": 1}
    assert body["total"] == 1


def test_a_category_bucket_carries_its_arxiv_name(client):
    body = client.get("/api/catalog/facets").json()

    assert {bucket["value"]: bucket["name"] for bucket in body["categories"]} == {
        "cs.CL": "Computation and Language",
        "cs.CV": "Computer Vision and Pattern Recognition",
    }
    assert all(bucket["name"] is None for bucket in body["months"] + body["holdings"])


def test_paging_stops_rather_than_offering_an_offset_past_the_end(client):
    first = client.get("/api/catalog/papers?limit=2").json()
    second = client.get(f"/api/catalog/papers?limit=2&offset={first['next_offset']}").json()

    assert first["next_offset"] == 2
    assert len(second["papers"]) == 1
    assert second["next_offset"] is None


@pytest.mark.parametrize("sort", ["newest", "oldest", "cited"])
def test_a_page_at_any_depth_is_that_slice_of_the_whole_order(client, sort):
    """The page's order is fixed by one query and its columns come from
    another; one-at-a-time pages must line up with the full list."""
    whole = [p["arxiv_id"] for p in client.get(f"/api/catalog/papers?sort={sort}").json()["papers"]]
    paged = [
        p["arxiv_id"]
        for offset in range(len(whole))
        for p in client.get(f"/api/catalog/papers?sort={sort}&limit=1&offset={offset}").json()[
            "papers"
        ]
    ]
    assert paged == whole


def test_an_offset_past_the_end_is_an_empty_page(client):
    body = client.get("/api/catalog/papers?offset=1000").json()
    assert body["papers"] == []
    assert body["next_offset"] is None


def test_no_chunk_text_reaches_this_surface(client):
    """§6c: the catalog abstract is metadata, chunk text is the paper. This
    route never reads `chunks`, and the response shape is the assertion."""
    body = client.get("/api/catalog/papers?holding=indexed").json()

    assert set(body["papers"][0]) == {
        "arxiv_id",
        "title",
        "authors",
        "abstract",
        "primary_category",
        "published",
        "version",
        "has_text",
        "indexed",
        "cited_by",
        "license",
    }


def test_fts_query_quotes_every_word_and_keeps_a_phrase_whole():
    assert routes_catalog.fts_query("chain of thought") == '"chain" AND "of" AND "thought"'
    assert routes_catalog.fts_query('"chain of thought" fast') == '"chain of thought" AND "fast"'
    assert routes_catalog.fts_query("cs.CL") == '"cs.CL"'
    assert routes_catalog.fts_query("!!!") is None


def test_the_holding_counts_say_what_each_choice_would_give(client):
    """The rail shows these beside the three choices, so they must be counted
    with the holding filter itself dropped, like every other dimension."""
    body = client.get("/api/catalog/facets?holding=indexed").json()

    assert {bucket["value"]: bucket["papers"] for bucket in body["holdings"]} == {
        "all": 3,
        "text": 2,
        "indexed": 1,
    }
    # `total` still answers for the filter as asked, holding included.
    assert body["total"] == 1


def test_the_licence_reaches_the_card_that_has_to_display_it(client):
    """D19: showing a crop of a CC paper is conditional on naming its licence
    beside the attribution, so the licence is on the wire for the card to
    print — not for the client to decide anything with."""
    papers = {
        p["arxiv_id"]: p["license"] for p in client.get("/api/catalog/papers").json()["papers"]
    }

    assert papers["2607.00001"] == "http://creativecommons.org/licenses/by/4.0/"
    assert papers["2608.00003"] is None
