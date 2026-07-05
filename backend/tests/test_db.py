"""Tests for askrag.db — corpus.db read-only BY CONSTRUCTION (spec §6).

Written before db.py existed: read-only-ness is a §6 hard-constraint surface,
so it is test-first per §4d, never test-after.
"""

import sqlite3

import pytest

from askrag import db


@pytest.fixture
def corpus_db(tmp_path):
    path = tmp_path / "corpus.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO papers VALUES ('2606.12345', 'A Paper')")
    conn.commit()
    conn.close()
    return path


def test_corpus_connection_reads(corpus_db):
    conn = db.connect_corpus(corpus_db)
    try:
        rows = conn.execute("SELECT arxiv_id, title FROM papers").fetchall()
        assert rows[0]["arxiv_id"] == "2606.12345"
    finally:
        conn.close()


def test_corpus_connection_rejects_insert(corpus_db):
    conn = db.connect_corpus(corpus_db)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO papers VALUES ('9999.00001', 'Injected')")
    finally:
        conn.close()


def test_corpus_connection_rejects_update_and_delete(corpus_db):
    conn = db.connect_corpus(corpus_db)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("UPDATE papers SET title = 'x'")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM papers")
    finally:
        conn.close()


def test_corpus_connection_rejects_ddl(corpus_db):
    conn = db.connect_corpus(corpus_db)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE exfil (x TEXT)")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DROP TABLE papers")
    finally:
        conn.close()


def test_corpus_connection_missing_file_raises_and_creates_nothing(tmp_path):
    # mode=ro must fail loudly on an absent corpus.db (it is produced only by
    # `just ingest`), and a read-only factory must never create files or dirs.
    missing = tmp_path / "not-ingested" / "corpus.db"
    with pytest.raises(sqlite3.OperationalError):
        db.connect_corpus(missing)
    assert not missing.parent.exists()


def test_traces_connection_reads_and_writes(tmp_path):
    path = tmp_path / "traces.db"
    conn = db.connect_traces(path)
    try:
        conn.execute("CREATE TABLE spend (day TEXT PRIMARY KEY, usd REAL)")
        conn.execute("INSERT INTO spend VALUES ('2026-07-04', 0.02)")
        conn.commit()
        rows = conn.execute("SELECT day, usd FROM spend").fetchall()
        assert rows[0]["usd"] == 0.02
    finally:
        conn.close()


def test_traces_connection_creates_parent_dir(tmp_path):
    # Fresh-deploy case: the DB's parent may be gitignored/absent, and
    # sqlite3.connect never creates parent directories (PR #40 lesson).
    path = tmp_path / "var" / "askrag" / "traces.db"
    conn = db.connect_traces(path)
    try:
        assert path.exists()
    finally:
        conn.close()
