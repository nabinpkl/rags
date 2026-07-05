"""Unit tests for arxiv_ingest storage plumbing (no network)."""
import arxiv_ingest as ai


def test_connect_creates_missing_db_parent_dir(tmp_path):
    # Fresh-clone case: corpus/ is gitignored, so the DB's parent directory
    # doesn't exist until connect() creates it (PR #40 review round 1 —
    # sqlite3.OperationalError on any collector command otherwise).
    db_path = tmp_path / "corpus" / "arxiv.db"
    conn = ai.connect(db_path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM papers").fetchone()
        assert count == 0
        assert db_path.exists()
    finally:
        conn.close()
