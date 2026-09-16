"""routes_census: only a month we hold whole may be spoken of as arXiv's output."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag.api import routes_census
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
        has_text=True,
    )


# 2607 and 2608 are held whole (4 of 4, 4 of 4). 2609 is the month the mirror
# has not published: 1 paper of a catalog 20, which is a gap in our collection
# and not a collapse in arXiv's output.
PAPERS = [
    _paper("2607.00001", "Vision one", "cs.CV"),
    _paper("2607.00002", "Vision two", "cs.CV"),
    _paper("2607.00003", "Language one", "cs.CL"),
    _paper("2607.00004", "Robotics one", "cs.RO"),
    _paper("2608.00001", "Vision three", "cs.CV"),
    _paper("2608.00002", "Language two", "cs.CL"),
    _paper("2608.00003", "Language three", "cs.CL"),
    _paper("2608.00004", "Security one", "cs.CR"),
    _paper("2609.00001", "September straggler", "cs.CL"),
]
CATALOG_MONTHS = {"2607": 4, "2608": 4, "2609": 20}
CHUNKS = [ChunkRow("2607.00001#0", "2607.00001", "__paper__", 1, 1, "vision", 3)]
CITED_WORKS = [
    CitedWorkRow("2607.00001", "Vision one", "A. Author", "cs.CV", 2026, "v1"),
    CitedWorkRow("2607.00003", "Language one", "A. Author", "cs.CL", 2026, "v1"),
    CitedWorkRow("1707.06347", "Proximal Policy Optimization", "J. S.", "cs.LG", 2017, "v2"),
]
# August cites two July papers; September cites one of them too, and must not
# be able to add to the August count.
CITATIONS = [
    ("2608.00001", "2607.00001"),
    ("2608.00002", "2607.00001"),
    ("2608.00003", "2607.00003"),
    ("2608.00004", "1707.06347"),
    ("2609.00001", "2607.00001"),
    ("2607.00002", "1707.06347"),
]


def _client(tmp_path, **overrides) -> TestClient:
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
        **overrides,
    )
    app = FastAPI()
    app.include_router(routes_census.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    _write_corpus_db(tmp_path / "corpus.db", PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)
    return _client(tmp_path)


def test_the_census_covers_only_the_months_we_hold_whole(client):
    body = client.get("/api/census/categories").json()

    assert [month["month"] for month in body["months"]] == ["2607", "2608"]
    # September is named rather than dropped: a month absent from a chart of
    # "what arXiv posted" reads as a month arXiv did not post in.
    assert body["excluded"] == [{"month": "2609", "papers_held": 1, "catalog_papers": 20}]


def test_every_month_reports_the_same_categories_in_the_same_order(client):
    body = client.get("/api/census/categories").json()

    # Ranked over the whole census (cs.CL 4, cs.CV 3, cs.CR 1, cs.RO 1), and
    # each month answers for all four, so the bars a reader compares across
    # months are the same bars.
    assert body["categories"] == ["cs.CL", "cs.CV", "cs.CR", "cs.RO"]
    for month in body["months"]:
        assert [share["category"] for share in month["categories"]] == body["categories"]
    july = body["months"][0]
    assert {s["category"]: s["papers"] for s in july["categories"]} == {
        "cs.CV": 2,
        "cs.CL": 1,
        "cs.RO": 1,
        "cs.CR": 0,
    }
    assert (july["papers"], july["catalog_papers"]) == (4, 4)


def test_categories_outside_the_shared_list_land_in_other_so_a_month_still_sums(tmp_path):
    _write_corpus_db(tmp_path / "corpus.db", PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)

    body = _client(tmp_path).get("/api/census/categories?top=1").json()

    july = body["months"][0]
    assert body["categories"] == ["cs.CL"]
    assert july["categories"][0]["papers"] + july["other"] == july["papers"]


def test_uptake_counts_the_next_month_citing_the_month_before_it(client):
    body = client.get("/api/census/uptake").json()

    assert (body["from_month"], body["to_month"]) == ("2607", "2608")
    # 2607.00001 twice, 2607.00003 once. The September citer is NOT counted:
    # it belongs to a month we do not hold, so including it would mix a
    # complete month's citers with a fraction of another's.
    assert [(w["work"]["arxiv_id"], w["citations_from"]) for w in body["works"]] == [
        ("2607.00001", 2),
        ("2607.00003", 1),
    ]
    # The work's own total travels with it: 2607.00001 has three citations in
    # the graph, two of which came from August. A row that showed only one of
    # those numbers would be read as the other.
    assert body["works"][0]["work"]["cited_by"] == 3
    assert (body["works_total"], body["edges_total"]) == (2, 3)


def test_uptake_is_empty_rather_than_wrong_when_no_two_complete_months_adjoin(tmp_path):
    papers = [_paper("2607.00001", "July"), _paper("2610.00001", "October")]
    _write_corpus_db(
        tmp_path / "corpus.db",
        papers,
        [],
        [CitedWorkRow("2607.00001", "July", "A.", "cs.CL", 2026, "v1")],
        [("2610.00001", "2607.00001")],
        {"2607": 1, "2610": 1},
    )

    body = _client(tmp_path).get("/api/census/uptake").json()

    # Both months are complete, but they are three months apart: October had a
    # quarter to find July's papers, which is not what "cited within weeks"
    # measures.
    assert body["from_month"] is None and body["works"] == []


def test_a_month_without_a_catalog_count_cannot_be_called_complete(tmp_path):
    _write_corpus_db(tmp_path / "corpus.db", PAPERS, CHUNKS, CITED_WORKS, CITATIONS, {"2607": 4})

    body = _client(tmp_path).get("/api/census/categories").json()

    # August has no census row, so its coverage is unknown; unknown coverage is
    # not coverage, however many papers we happen to hold.
    assert [month["month"] for month in body["months"]] == ["2607"]


def test_the_coverage_floor_is_configurable_and_actually_gates(tmp_path):
    _write_corpus_db(tmp_path / "corpus.db", PAPERS, CHUNKS, CITED_WORKS, CITATIONS, CATALOG_MONTHS)

    body = _client(tmp_path, landing_census_min_coverage=0.05).get("/api/census/categories").json()

    assert [month["month"] for month in body["months"]] == ["2607", "2608", "2609"]
    assert body["excluded"] == []


def test_next_month_rolls_the_year_over():
    assert routes_census.next_month("2612") == "2701"
    assert routes_census.next_month("2607") == "2608"


def _census_scan_counts(tmp_path, papers, catalog_months) -> tuple[int, int]:
    """How many full catalog passes one /api/census/categories request makes."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write_corpus_db(tmp_path / "corpus.db", papers, CHUNKS, CITED_WORKS, CITATIONS, catalog_months)
    calls = {"coverage": 0, "cohort": 0}
    with pytest.MonkeyPatch.context() as patch:
        for name, key in (("month_coverage", "coverage"), ("cohort_months", "cohort")):
            real = getattr(routes_census, name)

            def counted(*args, _real=real, _key=key, **kwargs):
                calls[_key] += 1
                return _real(*args, **kwargs)

            patch.setattr(routes_census, name, counted)
        assert _client(tmp_path).get("/api/census/categories").status_code == 200
    return calls["coverage"], calls["cohort"]


def test_the_catalog_is_scanned_a_fixed_number_of_times_whatever_the_month_count(tmp_path):
    """Regression: both sets were built inside the `excluded` comprehension, so
    every catalog month cost another full pass. 234 real months turned a 0.5s
    request into 55s, which the browser simply never waited for."""
    thin = [_paper(f"{year}{month:02d}.00001", "Older") for year in (24, 25) for month in (3, 9)]
    few = _census_scan_counts(tmp_path / "few", PAPERS, CATALOG_MONTHS)
    many = _census_scan_counts(
        tmp_path / "many",
        PAPERS + thin,
        CATALOG_MONTHS | {paper.arxiv_id[:4]: 400 for paper in thin},
    )
    assert few == many
