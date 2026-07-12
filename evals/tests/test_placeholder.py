"""Workspace-wiring smoke test (issue #79); #17 replaces this with test_golden_set.py."""

from evals.placeholder import HybridSearch, connect_corpus


def test_read_seams_importable():
    assert callable(connect_corpus)
    assert isinstance(HybridSearch, type)


def test_connect_corpus_opens_a_real_sqlite_file(tmp_path):
    db_path = tmp_path / "corpus.db"
    db_path.touch()
    conn = connect_corpus(db_path)
    try:
        assert tuple(conn.execute("SELECT 1").fetchone()) == (1,)
    finally:
        conn.close()
