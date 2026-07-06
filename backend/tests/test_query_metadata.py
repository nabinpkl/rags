"""Tests for askrag.tools.query_metadata — SELECT-only enforcement (§5/§6).

Security-relevant behavior, written test-first (§4d/§6 table): every one of
these must be refused before a single row is read, by construction
(sqlite3 authorizer + single-statement execute), never by string-matching
the model's SQL text.
"""

import time

import pytest

from askrag.config import Settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.tools.query_metadata import (
    QueryMetadataArgs,
    QueryMetadataError,
    QueryMetadataResult,
    run,
)


def paper(arxiv_id, year=2024):
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories="cs.CL",
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
    papers = [paper("2401.00001", 2024), paper("2401.00002", 2023)]
    chunks = [
        ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "hello world", 2),
        ChunkRow("2401.00002#0", "2401.00002", "Intro", 1, 1, "goodbye world", 2),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, chunks)
    return path


@pytest.fixture
def many_papers_db(tmp_path):
    # Big enough that a self cross-join blows a near-zero deadline (measured
    # locally: a 4-way join over 50 rows takes low milliseconds).
    papers = [paper(f"{i:04d}.00001", 2024) for i in range(50)]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, [])
    return path


def query(sql, corpus_db, **settings_overrides) -> QueryMetadataResult:
    return run(
        QueryMetadataArgs(sql=sql),
        settings=Settings(**settings_overrides),
        corpus_db_path=corpus_db,
    )


# --- the tool works for its intended purpose ---------------------------------


def test_plain_select_returns_columns_and_rows(corpus_db):
    result = query("SELECT arxiv_id, published FROM papers ORDER BY arxiv_id", corpus_db)
    assert result.columns == ("arxiv_id", "published")
    assert result.rows == (("2401.00001", "2024-01-01"), ("2401.00002", "2023-01-01"))
    assert result.truncated is False


def test_aggregate_and_join_work(corpus_db):
    result = query(
        "SELECT p.arxiv_id, COUNT(c.chunk_id) FROM papers p "
        "JOIN chunks c ON c.paper_id = p.arxiv_id GROUP BY p.arxiv_id",
        corpus_db,
    )
    assert set(result.rows) == {("2401.00001", 1), ("2401.00002", 1)}


# --- refused at parse time, not by keyword matching --------------------------


@pytest.mark.parametrize(
    "hostile_sql",
    [
        "INSERT INTO papers (arxiv_id) VALUES ('x')",
        "UPDATE papers SET title = 'pwned'",
        "DELETE FROM papers",
        "DROP TABLE papers",
        "PRAGMA table_info(papers)",
        "PRAGMA writable_schema=1",
        "ATTACH DATABASE ':memory:' AS aux",
        "CREATE TABLE evil (x)",
        # multi-statement: a trailing statement smuggled in after a valid SELECT
        "SELECT 1; DROP TABLE papers",
        "SELECT 1; SELECT 2",
    ],
)
def test_hostile_sql_is_refused(corpus_db, hostile_sql):
    with pytest.raises(QueryMetadataError):
        query(hostile_sql, corpus_db)


def test_trailing_comment_after_a_semicolon_is_not_a_second_statement(corpus_db):
    # SQLite treats a comment as no statement at all, not as smuggled second
    # SQL — this is the multi-statement guard's boundary, not a bypass: there
    # is genuinely only one statement here for `execute()` to run.
    result = query("SELECT 1; -- DROP TABLE papers", corpus_db)
    assert result.rows == ((1,),)


def test_a_single_trailing_semicolon_is_fine(corpus_db):
    # Multi-statement rejection must not misfire on the common single-query
    # trailing-semicolon style.
    result = query("SELECT arxiv_id FROM papers WHERE arxiv_id = '2401.00001';", corpus_db)
    assert result.rows == (("2401.00001",),)


def test_read_only_connection_refuses_writes_even_past_the_authorizer(corpus_db):
    # Defense in depth: db.connect_corpus() opens mode=ro (§4c) independent of
    # the authorizer, so even a hypothetical authorizer bypass hits a
    # read-only file at the SQLite level.
    with pytest.raises(QueryMetadataError):
        query("INSERT INTO papers (arxiv_id) VALUES ('should-never-land')", corpus_db)
    # No mutation happened: a fresh plain connection still sees 2 rows.
    result = query("SELECT COUNT(*) FROM papers", corpus_db)
    assert result.rows == ((2,),)


# --- limits: rows and time ----------------------------------------------------


def test_row_limit_truncates_and_reports_it(corpus_db):
    result = query("SELECT arxiv_id FROM papers", corpus_db, query_metadata_max_rows=1)
    assert len(result.rows) == 1
    assert result.truncated is True


def test_row_limit_not_hit_reports_false(corpus_db):
    result = query("SELECT arxiv_id FROM papers", corpus_db, query_metadata_max_rows=500)
    assert result.truncated is False


def test_slow_query_times_out(many_papers_db):
    # A 4-way self cross-join over 50 papers (~6M row-combinations) forces
    # enough VM steps to blow a near-zero deadline, independent of real
    # corpus size.
    start = time.monotonic()
    with pytest.raises(QueryMetadataError):
        query(
            "SELECT COUNT(*) FROM papers p1, papers p2, papers p3, papers p4",
            many_papers_db,
            query_metadata_timeout_seconds=0.001,
        )
    assert time.monotonic() - start < 5  # aborted promptly, not left to run


def test_generous_timeout_does_not_trip_a_normal_query(corpus_db):
    result = query("SELECT arxiv_id FROM papers", corpus_db, query_metadata_timeout_seconds=5.0)
    assert len(result.rows) == 2


# --- args schema ---------------------------------------------------------------


def test_args_reject_extra_fields():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        QueryMetadataArgs.model_validate({"sql": "SELECT 1", "extra_field": "nope"})


def test_args_reject_blank_sql():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        QueryMetadataArgs(sql="")
