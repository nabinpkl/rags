"""Tests for askrag.tools.query_metadata — enum'd metadata query ops (§5/§6).

No model-authored SQL exists anywhere in this tool (DECISIONS.md
2026-07-06): the old SQL-injection/DoS-refusal tests are gone — moot, there
is no SQL surface left to inject into. Security-relevant behavior here is
"the union accepts only these three shapes"; that is asserted directly by
`extra="forbid"` and the discriminator, tested below.

`count_papers` shares `askrag.facets.count_scalar`/`count_grouped` with
`GET /api/facets` (see module docstring on `askrag.facets`), so it inherits
the indexed-corpus scope those functions apply (D16, issue #73): the
fixture's 2401.00003 has no chunks and is excluded from every `count_papers`
result below. `corpus_stats` applies the same `INDEXED_PREDICATE` directly
to its own query, so its totals are excluded too — uniform scoping across
the whole `query_metadata` surface. `paper_facets` refuses a chunk-less id
outright: answering it would hand the agent a title, category and venue for a
paper it cannot read, which is the agent knowing the whole catalog by id.
"""

import pytest
from pydantic import ValidationError

from askrag.config import Settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.tools.query_metadata import (
    CorpusStatsResult,
    CountPapersResult,
    PaperFacetsResult,
    QueryMetadataArgs,
    QueryMetadataError,
    run,
)


def paper(arxiv_id, year=2024, category="cs.CL", license=None, venue=None):
    return PaperRow(
        arxiv_id=arxiv_id,
        title=f"title-{arxiv_id}",
        authors="a",
        abstract="x",
        categories=category,
        published=f"{year}-01-01",
        version="v1",
        license=license,
        venue=venue,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


@pytest.fixture
def corpus_db(tmp_path):
    papers = [
        paper("2401.00001", year=2024, category="cs.CL", license="CC-BY-4.0", venue="ACL"),
        paper("2401.00002", year=2023, category="cs.CL", license=None, venue=None),
        paper("2401.00003", year=2023, category="cs.LG", license="CC-BY-4.0", venue="NeurIPS"),
    ]
    chunks = [
        ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "hello", 2),
        ChunkRow("2401.00001#1", "2401.00001", "Body", 2, 3, "world", 2),
        ChunkRow("2401.00002#0", "2401.00002", "Intro", 1, 1, "goodbye", 2),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, chunks)
    return path


def query(op_payload: dict, corpus_db, **settings_overrides):
    return run(
        QueryMetadataArgs.model_validate(op_payload),
        settings=Settings(**settings_overrides),
        corpus_db_path=corpus_db,
    )


# --- count_papers -------------------------------------------------------------


def test_count_papers_scalar_with_no_filters(corpus_db):
    # 3 papers in `papers`, 2 indexed (2401.00003 has no chunks, D16 #73).
    result = query({"op": "count_papers"}, corpus_db)
    assert isinstance(result, CountPapersResult)
    assert result.count == 2
    assert result.histogram is None
    assert result.truncated is False


def test_count_papers_filters_bind_category_year_and_license(corpus_db):
    # 2401.00003 (cs.LG, chunk-less) matches this filter but isn't indexed.
    assert query({"op": "count_papers", "category": "cs.LG"}, corpus_db).count == 0
    assert query({"op": "count_papers", "year_min": 2024}, corpus_db).count == 1
    assert query({"op": "count_papers", "year_max": 2023}, corpus_db).count == 1
    assert query({"op": "count_papers", "has_license": True}, corpus_db).count == 1
    assert query({"op": "count_papers", "has_license": False}, corpus_db).count == 1
    assert (
        query({"op": "count_papers", "category": "cs.CL", "year_min": 2024}, corpus_db).count == 1
    )


def test_count_papers_histogram_by_category_excludes_a_chunkless_papers_bucket(corpus_db):
    result = query({"op": "count_papers", "group_by": "category"}, corpus_db)
    assert result.count is None
    buckets = {b.value: b.count for b in result.histogram}
    # cs.LG (2401.00003, chunk-less) never appears as a bucket at all.
    assert buckets == {"cs.CL": 2}
    assert result.truncated is False


def test_count_papers_histogram_by_license_groups_nulls_together(corpus_db):
    result = query({"op": "count_papers", "group_by": "license"}, corpus_db)
    buckets = {b.value: b.count for b in result.histogram}
    assert buckets == {"CC-BY-4.0": 1, None: 1}


def test_count_papers_histogram_by_year_and_venue(corpus_db):
    year_result = query({"op": "count_papers", "group_by": "year"}, corpus_db)
    by_year = {b.value: b.count for b in year_result.histogram}
    assert by_year == {2024: 1, 2023: 1}
    venue_result = query({"op": "count_papers", "group_by": "venue"}, corpus_db)
    by_venue = {b.value: b.count for b in venue_result.histogram}
    assert by_venue == {"ACL": 1, None: 1}


def test_count_papers_histogram_top_n_truncates_and_reports_it(corpus_db):
    # "category" only has 1 indexed bucket now (cs.LG's sole paper is
    # chunk-less) — "year" still has 2 (2024, 2023), so it exercises
    # truncation meaningfully.
    result = query(
        {"op": "count_papers", "group_by": "year"},
        corpus_db,
        query_metadata_histogram_max_groups=1,
    )
    assert len(result.histogram) == 1
    assert result.truncated is True


def test_count_papers_histogram_within_cap_reports_not_truncated(corpus_db):
    result = query(
        {"op": "count_papers", "group_by": "category"},
        corpus_db,
        query_metadata_histogram_max_groups=500,
    )
    assert result.truncated is False


def test_count_papers_off_enum_group_by_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "count_papers", "group_by": "not_a_real_column"})


# --- paper_facets ---------------------------------------------------------------


def test_paper_facets_returns_all_fields_incl_chunk_and_page_counts(corpus_db):
    result = query({"op": "paper_facets", "paper_id": "2401.00001"}, corpus_db)
    assert isinstance(result, PaperFacetsResult)
    assert result.paper_id == "2401.00001"
    assert result.title == "title-2401.00001"
    assert result.primary_category == "cs.CL"
    assert result.year == 2024
    assert result.version == "v1"
    assert result.license == "CC-BY-4.0"
    assert result.venue == "ACL"
    assert result.n_chunks == 2
    assert result.n_pages == 3  # max(page_end)


def test_paper_facets_refuses_a_catalog_paper_that_is_not_indexed(corpus_db):
    # 2401.00003 has a `papers` row and no chunks. The agent's corpus is the
    # indexed set (D16), so metadata for it would be knowledge of a paper the
    # agent cannot search or read.
    with pytest.raises(QueryMetadataError, match="2401.00003"):
        query({"op": "paper_facets", "paper_id": "2401.00003"}, corpus_db)


def test_paper_facets_unknown_id_raises(corpus_db):
    with pytest.raises(QueryMetadataError):
        query({"op": "paper_facets", "paper_id": "9999.99999"}, corpus_db)


# --- corpus_stats -----------------------------------------------------------------


def test_corpus_stats_totals_scoped_to_indexed_papers(corpus_db):
    # 2401.00003 (cs.LG, chunk-less) is excluded from n_papers and
    # n_categories; year_min/year_max happen to be unchanged here since
    # the excluded paper's year (2023) is also covered by an indexed one.
    result = query({"op": "corpus_stats"}, corpus_db)
    assert isinstance(result, CorpusStatsResult)
    assert result.n_papers == 2
    assert result.n_chunks == 3  # chunk rows only ever exist for indexed papers
    assert result.year_min == 2023
    assert result.year_max == 2024
    assert result.n_categories == 1


# --- to_model_payload is a plain JSON-shaped dict --------------------------------


def test_count_papers_scalar_payload_shape(corpus_db):
    result = query({"op": "count_papers"}, corpus_db)
    assert result.to_model_payload() == {"count": 2, "histogram": None, "truncated": False}


def test_count_papers_histogram_payload_shape(corpus_db):
    result = query({"op": "count_papers", "group_by": "category"}, corpus_db)
    payload = result.to_model_payload()
    assert payload["count"] is None
    assert payload["truncated"] is False
    assert {"value": "cs.CL", "count": 2} in payload["histogram"]


def test_paper_facets_payload_shape(corpus_db):
    result = query({"op": "paper_facets", "paper_id": "2401.00001"}, corpus_db)
    assert result.to_model_payload() == {
        "paper_id": "2401.00001",
        "title": "title-2401.00001",
        "primary_category": "cs.CL",
        "year": 2024,
        "version": "v1",
        "license": "CC-BY-4.0",
        "venue": "ACL",
        "n_chunks": 2,
        "n_pages": 3,
    }


def test_corpus_stats_payload_shape(corpus_db):
    result = query({"op": "corpus_stats"}, corpus_db)
    assert result.to_model_payload() == {
        "n_papers": 2,
        "n_chunks": 3,
        "year_min": 2023,
        "year_max": 2024,
        "n_categories": 1,
    }


# --- args schema: no raw-SQL path exists anywhere --------------------------------


def test_args_reject_a_free_form_sql_field():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "corpus_stats", "sql": "SELECT 1"})


def test_args_reject_unknown_op():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "run_raw_sql", "sql": "SELECT 1"})


def test_count_papers_rejects_extra_fields():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "count_papers", "unexpected": "nope"})


def test_paper_facets_requires_paper_id():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "paper_facets"})


def test_corpus_stats_rejects_any_params():
    with pytest.raises(ValidationError):
        QueryMetadataArgs.model_validate({"op": "corpus_stats", "paper_id": "2401.00001"})
