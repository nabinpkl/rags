"""routes_landing: counts are honest totals, lists are indexed-only (D16)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag import db
from askrag.api import routes_landing
from askrag.config import Settings, get_settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.ingest.resolve_cited_works import CitedWorkRow


def _paper(arxiv_id: str, title: str, cats: str = "cs.CL") -> PaperRow:
    return PaperRow(
        arxiv_id=arxiv_id,
        title=title,
        authors="A. Author",
        abstract="An abstract.",
        categories=cats,
        published=f"20{arxiv_id[:2]}-01-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


# Three citers in the window. 2608.00003 is deliberately NOT indexed: it has no
# chunks row, so it must be counted and never listed.
PAPERS = [
    _paper("2608.00001", "Indexed citer one"),
    _paper("2608.00002", "Indexed citer two"),
    _paper("2608.00003", "Unindexed citer"),
]
CHUNKS = [
    ChunkRow("2608.00001#0", "2608.00001", "__paper__", 1, 1, "reinforcement learning", 3),
    ChunkRow("2608.00002#0", "2608.00002", "__paper__", 1, 1, "policy optimization", 3),
]
CITED_WORKS = [
    CitedWorkRow("1707.06347", "Proximal Policy Optimization", "J. Schulman", "cs.LG", 2017, "v2"),
    CitedWorkRow("2402.03300", "DeepSeekMath", "Z. Shao", "cs.CL", 2024, "v3"),
    CitedWorkRow("9999.99999", None, None, None, None, None),  # unresolvable
]
CITATIONS = [
    ("2608.00001", "1707.06347"),
    ("2608.00002", "1707.06347"),
    ("2608.00003", "1707.06347"),  # the unindexed citer
    ("2608.00001", "2402.03300"),
    ("2608.00002", "2402.03300"),
    ("2608.00001", "9999.99999"),
]


@pytest.fixture
def client(tmp_path):
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS)
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
    )
    app = FastAPI()
    app.include_router(routes_landing.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_landing_stats_are_derived_from_the_graph(client):
    stats = client.get("/api/landing").json()["stats"]

    # The window is the id-month span of the CITING side — not a date written
    # down anywhere, so it cannot disagree with the data.
    assert (stats["window_start"], stats["window_end"]) == ("2608", "2608")
    assert stats["papers_in_window"] == 3
    assert stats["papers_with_references"] == 3
    assert stats["citations"] == 6
    assert stats["cited_works"] == 3


def test_foundations_rank_by_citation_count(client):
    foundations = client.get("/api/landing").json()["foundations"]

    assert [(f["arxiv_id"], f["cited_by"]) for f in foundations] == [
        ("1707.06347", 3),
        ("2402.03300", 2),
        ("9999.99999", 1),
    ]
    assert foundations[0]["title"] == "Proximal Policy Optimization"


def test_an_unresolvable_cited_work_still_counts(client):
    """Dropping it would understate every total; it appears with a null title."""
    foundations = client.get("/api/landing").json()["foundations"]
    unresolved = next(f for f in foundations if f["arxiv_id"] == "9999.99999")

    assert unresolved["title"] is None
    assert unresolved["cited_by"] == 1


def test_cited_years_show_how_far_back_the_cohort_reaches(client):
    buckets = client.get("/api/landing").json()["cited_years"]

    assert {(b["year"], b["citations"]) for b in buckets} == {(2017, 3), (2024, 2), (None, 1)}


def test_the_count_is_every_citer_but_the_list_is_indexed_only(client):
    """THE D16 line.

    3 papers cite PPO and the page says 3. Only 2 are indexed, so only 2 are
    listed — every link the reader can click opens.
    """
    detail = client.get("/api/foundations/1707.06347").json()

    assert detail["total_citers"] == 3
    assert detail["foundation"]["cited_by"] == 3
    listed = [c["arxiv_id"] for c in detail["indexed_citers"]]
    assert listed == ["2608.00002", "2608.00001"]  # newest first
    assert "2608.00003" not in listed


def test_no_readable_flag_reaches_the_wire(client):
    """D16 forbids a two-tier UI: the wire carries no indexed/readable field."""
    payload = client.get("/api/foundations/1707.06347").json()

    for citer in payload["indexed_citers"]:
        assert set(citer) == {"arxiv_id", "title", "primary_category", "version"}


def test_co_cited_counts_papers_citing_both(client):
    detail = client.get("/api/foundations/1707.06347").json()

    by_id = {w["arxiv_id"]: w["cite_both"] for w in detail["co_cited"]}
    # 2608.00001 and 2608.00002 cite both PPO and DeepSeekMath; 9999 only one.
    assert by_id == {"2402.03300": 2, "9999.99999": 1}


def test_a_work_is_never_co_cited_with_itself(client):
    detail = client.get("/api/foundations/1707.06347").json()

    assert "1707.06347" not in {w["arxiv_id"] for w in detail["co_cited"]}


def test_unknown_foundation_is_404(client):
    assert client.get("/api/foundations/1234.56789").status_code == 404


def test_scope_is_the_indexed_citers_plus_the_work_itself(tmp_path):
    """The ask surface's scope: server-resolved, never model-authored."""
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS)
    conn = db.connect_corpus(corpus_db)
    try:
        scope = routes_landing.scope_paper_ids(conn, "1707.06347")
    finally:
        conn.close()

    # PPO itself is not in `papers`, so it contributes nothing; the unindexed
    # citer is excluded because the agent could not read it anyway.
    assert scope == ("2608.00001", "2608.00002")


def test_scope_of_a_foundation_we_hold_includes_it(tmp_path):
    corpus_db = tmp_path / "corpus.db"
    papers = [*PAPERS, _paper("2402.03300", "DeepSeekMath, held")]
    chunks = [*CHUNKS, ChunkRow("2402.03300#0", "2402.03300", "__paper__", 1, 1, "grpo", 2)]
    _write_corpus_db(corpus_db, papers, chunks, CITED_WORKS, CITATIONS)
    conn = db.connect_corpus(corpus_db)
    try:
        scope = routes_landing.scope_paper_ids(conn, "2402.03300")
    finally:
        conn.close()

    assert scope == ("2402.03300", "2608.00001", "2608.00002")


def test_author_lists_are_trimmed_on_the_wire(tmp_path):
    """94% of an untrimmed /api/landing payload was authors the UI discards.

    A frontier-model report carries ~1,000 names; the page shows a handful.
    Trimming server-side means the wire carries what is displayed.
    """
    many = ", ".join(f"Author {n}" for n in range(50))
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(
        corpus_db,
        PAPERS,
        CHUNKS,
        [CitedWorkRow("1707.06347", "PPO", many, "cs.LG", 2017, "v2")],
        [("2608.00001", "1707.06347")],
    )
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        landing_max_authors=3,
        _env_file=None,  # ty: ignore[unknown-argument]
    )
    app = FastAPI()
    app.include_router(routes_landing.router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as tc:
        listed = tc.get("/api/landing").json()["foundations"][0]
        detail = tc.get("/api/foundations/1707.06347").json()["foundation"]

    assert listed["authors"] == "Author 0, Author 1, Author 2 +47"
    assert detail["authors"] == listed["authors"]


def test_a_short_author_list_is_left_alone():
    assert routes_landing.trim_authors("A. Author, B. Author", 6) == "A. Author, B. Author"
    assert routes_landing.trim_authors("A and B", 6) == "A, B"
    assert routes_landing.trim_authors(None, 6) is None


def test_landing_limit_defaults_to_the_frontier_manifest(tmp_path):
    """The page's length and the manifest's length are the same number.

    select_frontier indexes `frontier_top_cited` works; a route default that
    disagreed would hide foundations whose papers were fetched and embedded.
    """
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS)
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        frontier_top_cited=2,
        frontier_citers_per_work=1,
        _env_file=None,  # ty: ignore[unknown-argument]
    )
    app = FastAPI()
    app.include_router(routes_landing.router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as tc:
        foundations = tc.get("/api/landing").json()["foundations"]
        detail = tc.get("/api/foundations/1707.06347").json()

    assert [f["arxiv_id"] for f in foundations] == ["1707.06347", "2402.03300"]
    assert len(detail["indexed_citers"]) == 1
    # The count is still the honest total — only the list is capped (D16).
    assert detail["total_citers"] == 3


def test_scope_size_is_what_the_agent_reads_not_what_the_page_lists(client):
    """The page cannot say "answers come from the N papers listed".

    The list is capped for layout; the scope is every indexed paper citing the
    work. Conflating them made the UI state a false fact about the agent.
    """
    detail = client.get("/api/foundations/1707.06347?citers_limit=1").json()

    assert len(detail["indexed_citers"]) == 1  # capped for display
    assert detail["scope_size"] == 2  # both indexed citers are actually read
    assert detail["total_citers"] == 3  # and the honest total is unchanged


def test_scope_size_counts_the_foundation_itself_when_we_hold_it(tmp_path):
    corpus_db = tmp_path / "corpus.db"
    papers = [*PAPERS, _paper("2402.03300", "DeepSeekMath, held")]
    chunks = [*CHUNKS, ChunkRow("2402.03300#0", "2402.03300", "__paper__", 1, 1, "grpo", 2)]
    _write_corpus_db(corpus_db, papers, chunks, CITED_WORKS, CITATIONS)
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
    )
    app = FastAPI()
    app.include_router(routes_landing.router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as tc:
        detail = tc.get("/api/foundations/2402.03300").json()

    # 2 indexed citers + the work itself; matches scope_paper_ids exactly.
    assert detail["scope_size"] == 3
