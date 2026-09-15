"""routes_landing: counts are honest totals, lists are indexed-only (D16)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag import db
from askrag.api import routes_landing
from askrag.config import Settings, get_settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.ingest.resolve_cited_works import CitedWorkRow


def _paper(arxiv_id: str, title: str, cats: str = "cs.CL", *, has_text: bool = True) -> PaperRow:
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
        has_text=has_text,
    )


# Three citers in the cohort month. 2608.00003 is deliberately NOT indexed: it
# has no chunks row, so it must be counted and never listed. 1506.00001 is the
# rest of the corpus: a paper from the collector's older sample that we never
# extracted text from, so it was never offered to the reference parser.
PAPERS = [
    _paper("2608.00001", "Indexed citer one"),
    _paper("2608.00002", "Indexed citer two"),
    _paper("2608.00003", "Unindexed citer"),
    _paper("1506.00001", "Older sampled paper", has_text=False),
]
# The catalog census: how many cs papers arXiv posted in those id-months. We
# hold 3 of the 10 in 2608 and 1 of the 900 in 1506, which is the whole point
# of the table — neither number is stateable without it.
CATALOG_MONTHS = {"2608": 10, "1506": 900}
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


def _client_for(tmp_path, **overrides) -> TestClient:
    """A client over the corpus.db already written into `tmp_path`."""
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
        **overrides,
    )
    app = FastAPI()
    app.include_router(routes_landing.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)
    return _client_for(tmp_path)


def test_landing_stats_are_derived_from_the_graph(client):
    stats = client.get("/api/landing").json()["stats"]

    # The cohort is the id-months the parsed papers actually came from, and it
    # carries the catalog's own count for those months: the page can say "3 of
    # 10", never "every cs paper arXiv posted".
    assert (stats["cohort_start"], stats["cohort_end"]) == ("2608", "2608")
    assert stats["cohort_papers"] == 3
    assert stats["cohort_catalog_papers"] == 10
    # The rest of the corpus is stated separately, not folded into the cohort.
    assert stats["corpus_papers"] == 4
    # THE parse-rate denominator: 3 papers reached the parser, not 4.
    assert stats["papers_parsed"] == 3
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
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)
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
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)
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


def test_latest_lists_newest_indexed_papers_with_reference_counts(client):
    """The dashboard's "what just landed" list. 2608.00003 is counted in the
    stats but never listed: it has no chunks, so linking it would dead-end
    (D16 — the same rule as indexed_citers)."""
    papers = client.get("/api/latest").json()["papers"]

    # Same published date, so arxiv_id breaks the tie, newest first.
    assert [p["arxiv_id"] for p in papers] == ["2608.00002", "2608.00001"]
    assert [p["ref_count"] for p in papers] == [2, 3]
    assert all(p["published"] == "2026-01-01" for p in papers)


def test_latest_limit_caps_the_list(client):
    papers = client.get("/api/latest?limit=1").json()["papers"]

    assert [p["arxiv_id"] for p in papers] == ["2608.00002"]


def test_coverage_states_what_we_hold_against_what_arxiv_posted(client):
    """The provenance panel's input. Counts are honest totals (CohortStats
    posture): every paper and edge lands in its id-month, indexed or not, and
    each month carries the catalog's own total so a bar cannot be read as a
    fact about the month rather than about our collection."""
    months = client.get("/api/coverage").json()["months"]

    assert months == [
        {
            "month": "1506",
            "papers_held": 1,
            "papers_parsed": 0,
            "refs_made": 0,
            "catalog_papers": 900,
        },
        {
            "month": "2608",
            "papers_held": 3,
            "papers_parsed": 3,
            "refs_made": 6,
            "catalog_papers": 10,
        },
    ]


def test_a_census_below_our_holdings_reports_unknown_not_over_100_percent(tmp_path):
    """A snapshot older than the month it is asked about cannot be its
    denominator. Unknown is printable; 233 of 0 is not."""
    corpus_db = tmp_path / "corpus.db"
    _write_corpus_db(corpus_db, PAPERS, CHUNKS, CITED_WORKS, CITATIONS, {"2608": 2})
    client = _client_for(tmp_path)

    (month,) = [m for m in client.get("/api/coverage").json()["months"] if m["month"] == "2608"]
    assert month["papers_held"] == 3
    assert month["catalog_papers"] is None
    assert client.get("/api/landing").json()["stats"]["cohort_catalog_papers"] is None


def test_a_stray_older_citer_does_not_widen_the_cohort(tmp_path):
    """THE bug the cohort rule replaces: the window was min/max of the citing
    id-month, so 261 stray seed papers (1.5% of the citing side) stretched the
    page's claim from two months to nineteen years."""
    corpus_db = tmp_path / "corpus.db"
    papers = [*PAPERS, _paper("1206.00001", "A stray old citer")]
    citations = [*CITATIONS, ("1206.00001", "1707.06347")]
    _write_corpus_db(corpus_db, papers, CHUNKS, CITED_WORKS, citations, CATALOG_MONTHS)
    # 1 stray of 4 parsed papers is 25%, so the threshold has to exclude it
    # explicitly here; against the real graph the same stray months sit at
    # 0.24% and below against a 1% floor.
    client = _client_for(tmp_path, landing_cohort_min_share=0.3)

    stats = client.get("/api/landing").json()["stats"]
    assert (stats["cohort_start"], stats["cohort_end"]) == ("2608", "2608")
    assert stats["papers_with_references"] == 4  # the stray is still counted
