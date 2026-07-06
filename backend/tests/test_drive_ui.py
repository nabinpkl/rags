"""Tests for askrag.tools.drive_ui — enum + DB validation (§5/§6)."""

import pytest

from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.tools.drive_ui import (
    DriveUiArgs,
    DriveUiError,
    GotoPageArgs,
    OpenPaperArgs,
    SetFiltersArgs,
    run,
)


def paper(arxiv_id, cats="cs.CL", year=2024):
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories=cats,
        published=f"{year}-01-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


@pytest.fixture
def corpus_db(tmp_path):
    papers = [paper("2401.00001", "cs.CL", 2024), paper("2401.00002", "cs.DS", 2023)]
    chunks = [
        ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 2, "hello", 1),
        ChunkRow("2401.00001#1", "2401.00001", "Method", 3, 5, "world", 1),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, chunks)
    return path


# --- open_paper ----------------------------------------------------------------


def test_open_paper_accepts_an_existing_id(corpus_db):
    result = run(
        DriveUiArgs.model_validate({"action": "open_paper", "paper_id": "2401.00001"}),
        corpus_db_path=corpus_db,
    )
    assert result == OpenPaperArgs(paper_id="2401.00001")


def test_open_paper_refuses_a_nonexistent_id(corpus_db):
    with pytest.raises(DriveUiError, match="9999.99999"):
        run(
            DriveUiArgs.model_validate({"action": "open_paper", "paper_id": "9999.99999"}),
            corpus_db_path=corpus_db,
        )


# --- goto_page -------------------------------------------------------------------


def test_goto_page_accepts_a_page_within_range(corpus_db):
    result = run(
        DriveUiArgs.model_validate({"action": "goto_page", "paper_id": "2401.00001", "page": 4}),
        corpus_db_path=corpus_db,
    )
    assert result == GotoPageArgs(paper_id="2401.00001", page=4)


def test_goto_page_refuses_a_nonexistent_paper_id(corpus_db):
    with pytest.raises(DriveUiError, match="9999.99999"):
        run(
            DriveUiArgs.model_validate(
                {"action": "goto_page", "paper_id": "9999.99999", "page": 1}
            ),
            corpus_db_path=corpus_db,
        )


def test_goto_page_refuses_a_page_past_the_papers_last_page(corpus_db):
    # 2401.00001's chunks end at page 5 — page 6 does not exist.
    with pytest.raises(DriveUiError, match="page 6"):
        run(
            DriveUiArgs.model_validate(
                {"action": "goto_page", "paper_id": "2401.00001", "page": 6}
            ),
            corpus_db_path=corpus_db,
        )


# --- set_filters -------------------------------------------------------------------


def test_set_filters_accepts_an_existing_category(corpus_db):
    result = run(
        DriveUiArgs.model_validate({"action": "set_filters", "category": "cs.CL"}),
        corpus_db_path=corpus_db,
    )
    assert result == SetFiltersArgs(category="cs.CL")


def test_set_filters_refuses_a_category_with_no_papers(corpus_db):
    with pytest.raises(DriveUiError, match="cs.LG"):
        run(
            DriveUiArgs.model_validate({"action": "set_filters", "category": "cs.LG"}),
            corpus_db_path=corpus_db,
        )


def test_set_filters_with_no_category_needs_no_db_check(corpus_db):
    result = run(
        DriveUiArgs.model_validate({"action": "set_filters", "year_min": 2020}),
        corpus_db_path=corpus_db,
    )
    assert result == SetFiltersArgs(year_min=2020)


# --- enum + closed-schema enforcement -----------------------------------------


def test_unknown_action_is_rejected_at_validation():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        DriveUiArgs.model_validate({"action": "delete_everything"})


def test_open_paper_cannot_carry_goto_page_fields():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        DriveUiArgs.model_validate({"action": "open_paper", "paper_id": "x", "page": 3})


def test_url_or_html_style_args_are_rejected_by_the_closed_schema():
    # There is no field named url/html/href anywhere in the schema, so a
    # model attempt to smuggle one is a plain extra-field rejection.
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        DriveUiArgs.model_validate(
            {"action": "open_paper", "paper_id": "2401.00001", "url": "javascript:alert(1)"}
        )
