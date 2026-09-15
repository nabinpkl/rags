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


# --- mirror-status: did a new batch land? (listing stubbed, no network) -------


def _stub_mirror(monkeypatch, tmp_path, *, written: str, watermark: str):
    """One month folder holding two PDFs of one paper, both written together."""
    monkeypatch.setattr(ai, "gcs_months", lambda session: ["2608", "2609"])
    monkeypatch.setattr(
        ai,
        "gcs_month_entries",
        lambda session, yymm: iter(
            [("2609.04203", 1, 1024, written), ("2609.04203", 2, 2048, written)]
        ),
    )
    connect, db = ai.connect, tmp_path / "arxiv.db"
    conn = connect(db)
    ai.set_state(conn, "last_until", watermark)
    conn.commit()
    conn.close()
    monkeypatch.setattr(ai, "connect", lambda *a, **k: connect(db))


def test_mirror_status_reports_a_batch_written_after_the_watermark(
    monkeypatch, tmp_path, capsys
):
    _stub_mirror(monkeypatch, tmp_path, written="2026-09-20T10:04:12Z",
                 watermark="2026-09-13")
    ai.run_mirror_status()
    out = capsys.readouterr().out
    assert "newest 2609" in out
    assert "1 ids / 2 pdfs" in out          # versions are PDFs, not papers
    assert "NEW: written after our watermark 2026-09-13" in out


def test_mirror_status_does_not_call_a_higher_top_id_new(monkeypatch, tmp_path, capsys):
    """The timestamp is the signal. Our store is category-filtered, so the
    mirror's top id sits above ours on every archive, batch or no batch."""
    _stub_mirror(monkeypatch, tmp_path, written="2026-09-06T10:04:12Z",
                 watermark="2026-09-13")
    ai.run_mirror_status()
    out = capsys.readouterr().out
    assert "nothing since our watermark 2026-09-13" in out
    assert "NEW" not in out


def _stub_store_and_seed(monkeypatch, tmp_path, *, held, catalog):
    """A store holding `held` and a seed listing `catalog` (id -> categories)."""
    connect, db = ai.connect, tmp_path / "arxiv.db"
    conn = connect(db)
    for aid in held:
        ai.upsert_paper(conn, {"arxiv_id": aid, "title": "t", "authors": "", "abstract": "",
                               "categories": "cs.LG", "datestamp": "", "published": "",
                               "version": "v1", "pdf_path": "", "size_bytes": 0,
                               "fetched_at": ""})
    conn.commit()
    conn.close()
    monkeypatch.setattr(ai, "connect", lambda *a, **k: connect(db))
    monkeypatch.setattr(ai, "seed_records", lambda path, **kw: iter(
        [{"arxiv_id": aid, "categories": cats} for aid, cats in catalog.items()]))


def test_missing_ids_names_what_the_catalog_has_and_the_store_does_not(
    monkeypatch, tmp_path, capsys
):
    # The papers a date-windowed backfill leaves behind: announced in the
    # month, submitted before it. Only the id-month can find them.
    _stub_store_and_seed(
        monkeypatch, tmp_path,
        held=["2608.00001"],
        catalog={"2608.00001": "cs.LG", "2608.00002": "cs.CL", "2608.00003": "math.PR",
                 "2607.00009": "cs.AI", "2609.00001": "cs.LG"},
    )

    ai.run_missing_ids(seed_file="seed.zip", months=["2607", "2608"], category_prefix="cs")

    out, err = capsys.readouterr()
    # cs only, the requested months only, and never a paper we already hold.
    assert out.split() == ["2607.00009", "2608.00002"]
    assert "2608: 1 of 2 held, 1 missing" in err


def test_missing_ids_writes_a_file_fetch_ids_can_read(monkeypatch, tmp_path):
    _stub_store_and_seed(monkeypatch, tmp_path, held=[],
                         catalog={"2608.00002": "cs.CL"})
    out = tmp_path / "missing.txt"

    ai.run_missing_ids(seed_file="seed.zip", months=["2608"], category_prefix="cs",
                       out=str(out))

    assert out.read_text(encoding="utf-8") == "2608.00002\n"


def test_missing_ids_refuses_a_month_that_is_not_an_id_month(monkeypatch, tmp_path):
    _stub_store_and_seed(monkeypatch, tmp_path, held=[], catalog={})

    with pytest.raises(SystemExit):
        # "2026-08" is a date, not an id-month; silently matching nothing
        # would report a clean store for a month we hold nothing of.
        ai.run_missing_ids(seed_file="seed.zip", months=["2026-08"], category_prefix="cs")
