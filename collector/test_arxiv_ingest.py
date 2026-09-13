"""Unit tests for arxiv_ingest storage plumbing (no network)."""
import sqlite3

import pytest

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


# --- D18: no code path touches export.arxiv.org -------------------------------


def test_harvest_is_retired():
    with pytest.raises(NotImplementedError, match="D18"):
        ai.harvest(None, oai_set="cs", frm="2026-08-23", until="2026-09-13")


def test_pdf_url_builder_is_retired():
    with pytest.raises(NotImplementedError, match="D18"):
        ai.pdf_url("2401.00001")


def test_fetch_pdf_refuses_arxiv_source():
    with pytest.raises(NotImplementedError, match="D18"):
        ai.fetch_pdf(None, {"arxiv_id": "2401.00001", "version": "v1"}, "arxiv")


def test_fetch_pdf_gcs_miss_is_skipped_never_refetched(monkeypatch):
    """A GCS miss ends the fetch; the arXiv fallback is gone (D18)."""
    monkeypatch.setattr(ai, "download_pdf", lambda *a, **k: None)
    assert (
        ai.fetch_pdf(None, {"arxiv_id": "2401.00001", "version": "v1"}, "gcs-only")
        is None
    )


def test_fetch_pdf_gcs_hit_still_works(monkeypatch, tmp_path):
    dest = tmp_path / "2401.00001.pdf"
    monkeypatch.setattr(ai, "download_pdf", lambda *a, **k: dest)
    assert (
        ai.fetch_pdf(None, {"arxiv_id": "2401.00001", "version": "v1"}, "gcs-only")
        == dest
    )


def test_run_without_seed_file_is_retired(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "PDF_DIR", tmp_path)
    monkeypatch.setattr(ai, "connect", lambda *a, **k: sqlite3.connect(":memory:"))
    with pytest.raises(NotImplementedError, match="--seed-file"):
        ai.run(
            oai_set="cs",
            frm="2026-08-23",
            until="2026-09-13",
            max_gb=None,
            limit=1,
            category_prefix="cs.CL",
            seed_file=None,
        )


def test_update_command_is_retired():
    with pytest.raises(NotImplementedError, match="D18"):
        ai.main(["update", "--set", "cs"])
