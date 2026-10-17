"""Tests for askrag.retrieval.index_schema: the contract any source meets (D21).

These build an index with NO arXiv tables at all, through `create_tables`,
and search it with the same legs the arXiv corpus uses: the generality claim
at the SQL level.
"""

import sqlite3

import pytest

from askrag.config import Settings
from askrag.retrieval import fts, index_schema
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import HybridSearch
from askrag.retrieval.index_location import IndexLocation


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def index_db(tmp_path):
    path = tmp_path / "index.db"
    conn = sqlite3.connect(path)
    index_schema.create_tables(conn)
    conn.executemany(
        "INSERT INTO rag_documents VALUES (?,?,?,?)",
        [("s1", "fix the deploy", 20261001, None), ("s2", "map labels", 20261015, None)],
    )
    conn.executemany(
        "INSERT INTO rag_chunks(chunk_id, doc_id, section, pos_start, pos_end, text, n_tokens)"
        " VALUES (?,?,?,?,?,?,?)",
        [
            ("s1#0", "s1", "deploy", 1, 2, "caddy returns 404 for the paper map", 8),
            ("s2#0", "s2", "labels", 1, 1, "group labels vanish on zoom in the paper map", 9),
            ("s2#1", "s2", "labels", 3, 4, "deck.gl text layer collision", 5),
        ],
    )
    conn.execute("INSERT INTO rag_chunks_fts(rowid, text) SELECT chunk_rowid, text FROM rag_chunks")
    conn.executemany(
        "INSERT INTO rag_facets VALUES (?,?,?)",
        [("s1", "project", "rags"), ("s2", "project", "rags"), ("s2", "branch", "main")],
    )
    conn.commit()
    conn.close()
    return path


def connect(path):
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def test_created_tables_meet_the_contract(index_db):
    conn = connect(index_db)
    try:
        index_schema.check(conn)
    finally:
        conn.close()


def test_check_names_a_missing_relation_and_a_missing_column(tmp_path):
    conn = sqlite3.connect(tmp_path / "bad.db")
    with pytest.raises(index_schema.IndexContractError, match="no rag_documents"):
        index_schema.check(conn)
    index_schema.create_tables(conn)
    conn.execute("DROP TABLE rag_facets")
    conn.execute("CREATE TABLE rag_facets (doc_id TEXT, key TEXT)")
    with pytest.raises(index_schema.IndexContractError, match="rag_facets lacks column"):
        index_schema.check(conn)
    conn.close()


def test_bm25_filters_by_facet_day_and_scope(index_db):
    conn = connect(index_db)
    try:
        everything = fts.search_bm25(conn, "paper map", 10, Filters())
        on_main = fts.search_bm25(conn, "paper map", 10, Filters(facets=(("branch", "main"),)))
        early = fts.search_bm25(conn, "paper map", 10, Filters(day_max=20261010))
        scoped = fts.search_bm25(conn, "paper map", 10, Filters(doc_ids=("s1",)))
        nowhere = fts.search_bm25(conn, "paper map", 10, Filters(facets=(("project", "x"),)))
    finally:
        conn.close()
    assert set(everything) == {"s1#0", "s2#0"}
    assert on_main == ["s2#0"]
    assert early == ["s1#0"]
    assert scoped == ["s1#0"]
    assert nowhere == []


class NoVectors:
    def query(self, embedding, k, *, filters):
        return []


class FixedEmbedder:
    def embed_query_priced(self, text):
        return [1.0], None


def test_hybrid_search_hydrates_a_non_arxiv_index(index_db):
    searcher = HybridSearch(
        Settings(rerank_enabled=False),
        IndexLocation(index_db, index_db.parent / "chroma", "unused"),
        embedder=FixedEmbedder(),
        vector_store=NoVectors(),
    )
    hits = searcher.search("text layer collision", k=3)
    assert [(h.doc_id, h.section, h.pos_start, h.pos_end, h.version) for h in hits][0] == (
        "s2",
        "labels",
        3,
        4,
        None,
    )
