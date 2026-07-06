"""Tests for askrag.retrieval.fts — BM25 leg, escaping written FIRST (§6)."""

import sqlite3

import pytest

from askrag.retrieval import fts

# --- escaping: user queries must never reach FTS5 as syntax (§6) -------------
# Written before the implementation (security-relevant is never test-after).


@pytest.mark.parametrize(
    "hostile",
    [
        'attention" OR chunk_id: *',  # operator + column-filter injection
        "a AND b OR c NOT d",  # bare boolean keywords
        "NEAR(a b, 5)",  # NEAR function syntax
        "^anchored",  # initial-token anchor
        "wild*card",  # prefix operator
        "(paren) {brace} [bracket]",
        "col:value",  # column filter
        '"unbalanced quote',
        "-minus +plus",
        "semi;colon 'quote' --comment",
    ],
)
def test_hostile_input_is_neutralized(fts_db, hostile):
    # The contract: ANY string is a safe MATCH expression after build_match_query
    # — worst case zero rows, never an fts5 syntax error, never a column filter.
    conn = sqlite3.connect(fts_db)
    match = fts.build_match_query(hostile)
    conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (match,)).fetchall()
    conn.close()  # reaching here without OperationalError IS the assertion


def test_quotes_inside_terms_are_doubled():
    # 'say' -> '"say"'; '"hi"' -> quotes doubled then wrapped -> '"""hi"""'
    assert fts.build_match_query('say "hi"') == '"say" OR """hi"""'


def test_terms_are_quoted_and_or_joined():
    # OR semantics: natural-language queries should rank partial matches,
    # not demand every term (FTS5 default is implicit AND).
    assert fts.build_match_query("chain of thought") == '"chain" OR "of" OR "thought"'


def test_empty_and_whitespace_queries_become_empty():
    assert fts.build_match_query("") == ""
    assert fts.build_match_query("   ") == ""


# --- the BM25 leg over a real (tmp) corpus.db --------------------------------


@pytest.fixture
def fts_db(tmp_path):
    """A corpus.db with the real build_indexes schema (knowledge lives once)."""
    from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db

    def paper(arxiv_id, cats, year):
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

    papers = [
        paper("2401.00001", "cs.CL cs.AI", 2024),
        paper("2401.00002", "cs.DS", 2024),
        paper("1901.00003", "cs.CL", 2019),
    ]
    chunks = [
        ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "attention is all you need", 5),
        ChunkRow("2401.00001#1", "2401.00001", "Method", 2, 3, "chain of thought prompting", 5),
        ChunkRow("2401.00002#0", "2401.00002", "Intro", 1, 1, "graph attention networks", 4),
        ChunkRow("1901.00003#0", "1901.00003", "Intro", 1, 2, "attention for translation", 4),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, chunks)
    return path


def connect(path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def test_bm25_leg_returns_rank_ordered_chunk_ids(fts_db):
    conn = connect(fts_db)
    hits = fts.search_bm25(conn, "attention networks", k=10)
    conn.close()
    assert hits[0] == "2401.00002#0"  # matches both terms, ranks first
    assert set(hits) == {"2401.00001#0", "2401.00002#0", "1901.00003#0"}


def test_bm25_category_filter_pushes_into_sql(fts_db):
    conn = connect(fts_db)
    hits = fts.search_bm25(conn, "attention", k=10, category="cs.CL")
    conn.close()
    assert set(hits) == {"2401.00001#0", "1901.00003#0"}  # cs.DS paper excluded


def test_bm25_year_range_filter(fts_db):
    conn = connect(fts_db)
    hits = fts.search_bm25(conn, "attention", k=10, year_min=2024)
    only_old = fts.search_bm25(conn, "attention", k=10, year_max=2019)
    conn.close()
    assert set(hits) == {"2401.00001#0", "2401.00002#0"}
    assert only_old == ["1901.00003#0"]


def test_bm25_k_caps_results_and_empty_query_returns_nothing(fts_db):
    conn = connect(fts_db)
    assert len(fts.search_bm25(conn, "attention", k=1)) == 1
    assert fts.search_bm25(conn, "   ", k=10) == []
    conn.close()
