"""Tests for askrag.facets — the shared group-by counting helper behind
query_metadata's count_papers group_by and GET /api/facets (D-2, issue #27)."""

import sqlite3

import pytest

from askrag.facets import CountFilters, count_grouped, count_scalar
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db


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
    chunks = [ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "hello", 2)]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, chunks)
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


# --- count_scalar -------------------------------------------------------------


def test_count_scalar_with_no_filters(corpus_db):
    assert count_scalar(corpus_db, CountFilters()) == 3


def test_count_scalar_filters_bind_category_year_and_license(corpus_db):
    assert count_scalar(corpus_db, CountFilters(category="cs.LG")) == 1
    assert count_scalar(corpus_db, CountFilters(year_min=2024)) == 1
    assert count_scalar(corpus_db, CountFilters(year_max=2023)) == 2
    assert count_scalar(corpus_db, CountFilters(has_license=True)) == 2
    assert count_scalar(corpus_db, CountFilters(has_license=False)) == 1
    assert count_scalar(corpus_db, CountFilters(category="cs.CL", year_min=2024)) == 1


# --- count_grouped --------------------------------------------------------------


def test_count_grouped_by_category(corpus_db):
    buckets, truncated = count_grouped(corpus_db, "category", CountFilters(), max_groups=10)
    assert truncated is False
    assert {(b.value, b.count) for b in buckets} == {("cs.CL", 2), ("cs.LG", 1)}


def test_count_grouped_orders_by_count_descending(corpus_db):
    buckets, _ = count_grouped(corpus_db, "category", CountFilters(), max_groups=10)
    assert buckets[0].value == "cs.CL"
    assert buckets[0].count == 2


def test_count_grouped_by_year_license_venue(corpus_db):
    by_year, _ = count_grouped(corpus_db, "year", CountFilters(), max_groups=10)
    assert {(b.value, b.count) for b in by_year} == {(2024, 1), (2023, 2)}

    by_license, _ = count_grouped(corpus_db, "license", CountFilters(), max_groups=10)
    assert {(b.value, b.count) for b in by_license} == {("CC-BY-4.0", 2), (None, 1)}

    by_venue, _ = count_grouped(corpus_db, "venue", CountFilters(), max_groups=10)
    assert {(b.value, b.count) for b in by_venue} == {("ACL", 1), ("NeurIPS", 1), (None, 1)}


def test_count_grouped_applies_filters_before_grouping(corpus_db):
    buckets, _ = count_grouped(corpus_db, "category", CountFilters(year_max=2023), max_groups=10)
    assert {(b.value, b.count) for b in buckets} == {("cs.CL", 1), ("cs.LG", 1)}


def test_count_grouped_truncates_at_max_groups_and_flags_it(corpus_db):
    buckets, truncated = count_grouped(corpus_db, "category", CountFilters(), max_groups=1)
    assert len(buckets) == 1
    assert truncated is True
    buckets_full, truncated_full = count_grouped(
        corpus_db, "category", CountFilters(), max_groups=2
    )
    assert len(buckets_full) == 2
    assert truncated_full is False
