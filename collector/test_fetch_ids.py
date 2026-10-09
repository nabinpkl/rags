"""fetch_ids: pulling a NAMED list off the mirror, as opposed to discovering one."""

import json

import fetch_ids


def test_reads_a_plain_id_list(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("2505.09388\n1707.06347\n\n", encoding="utf-8")

    assert fetch_ids.read_ids(path) == ["2505.09388", "1707.06347"]


def test_reads_a_frontier_manifest(tmp_path):
    """The manifest is the normal input — it IS the list of papers to hold."""
    path = tmp_path / "frontier.json"
    path.write_text(
        json.dumps(
            {
                "rule": {"top_cited": 2, "citers_per_work": 2},
                "cited_works": ["1707.06347"],
                "citers": {"1707.06347": ["2608.00001"]},
                "paper_ids": ["1707.06347", "2608.00001"],
            }
        ),
        encoding="utf-8",
    )

    assert fetch_ids.read_ids(path) == ["1707.06347", "2608.00001"]


def test_a_dry_run_touches_neither_network_nor_store(tmp_path, monkeypatch, capsys):
    """Resume is a SELECT per id, not a download — a dry run must prove that."""

    class FakeConn:
        closed = False

        def close(self):
            FakeConn.closed = True

    monkeypatch.setattr(fetch_ids.ai, "connect", lambda: FakeConn())
    monkeypatch.setattr(fetch_ids.ai, "already_ingested", lambda conn, aid: aid.startswith("1707"))

    def refuse(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a dry run must not read the seed or hit the network")

    monkeypatch.setattr(fetch_ids.ai, "seed_records", refuse)
    monkeypatch.setattr(fetch_ids.ai, "download_pdf", refuse)

    assert fetch_ids.fetch(["1707.06347", "2505.09388"], concurrency=1, dry_run=True) == 0

    report = capsys.readouterr().err
    assert "2 ids requested, 1 already ingested, 1 to fetch" in report
    assert FakeConn.closed


def test_downloads_through_the_real_download_pdf_signature(tmp_path, monkeypatch, capsys):
    """The fetch path calls arxiv_ingest.download_pdf, and drift there is silent.

    D18 dropped its `pace` keyword and updated every call site inside
    arxiv_ingest.py, but not this one; the dry-run test's stub took **kwargs,
    so nothing failed until a frontier rebuild had a paper to fetch and died
    on TypeError. The stub below carries the REAL signature for that reason.
    """
    pdf = tmp_path / "pdfs" / "2505.09388.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 fixture")
    stored: list[dict] = []

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(fetch_ids.ai, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(fetch_ids.ai, "connect", lambda: FakeConn())
    monkeypatch.setattr(fetch_ids.ai, "already_ingested", lambda conn, aid: False)
    monkeypatch.setattr(
        fetch_ids.ai,
        "seed_records",
        lambda path: iter(
            [{"arxiv_id": "2505.09388", "title": "Qwen3 Technical Report", "version": "v1"}]
        ),
    )
    monkeypatch.setattr(fetch_ids.ai, "thread_session", lambda: object())
    monkeypatch.setattr(fetch_ids.ai, "upsert_paper", lambda conn, rec: stored.append(rec))

    def download_pdf(session, arxiv_id, url):  # the real signature, positionally
        assert url.endswith("2505.09388v1.pdf")
        return pdf

    monkeypatch.setattr(fetch_ids.ai, "download_pdf", download_pdf)

    assert fetch_ids.fetch(["2505.09388"], concurrency=1, dry_run=False) == 0
    assert [rec["arxiv_id"] for rec in stored] == ["2505.09388"]
    assert stored[0]["pdf_path"] == "pdfs/2505.09388.pdf"
    assert "stored 1 of 1" in capsys.readouterr().err


def test_falls_back_to_the_newest_version_the_mirror_actually_carries(
    tmp_path, monkeypatch, capsys
):
    """The snapshot pins the paper's latest version; the mirror lags it.

    Measured on the July/August top-up: 262 of 1,355 ids had no PDF at the
    pinned version, 205 of them at v2. The paper is on the mirror, one
    version back, and the stored version has to be the one we hold because
    the UI version-pins its arxiv.org links (§6b).
    """
    pdf = tmp_path / "pdfs" / "2608.31115.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 fixture")
    stored: list[dict] = []
    listings: list[str] = []

    class FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(fetch_ids, "_month_versions", {})
    monkeypatch.setattr(fetch_ids.ai, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(fetch_ids.ai, "connect", lambda: FakeConn())
    monkeypatch.setattr(fetch_ids.ai, "already_ingested", lambda conn, aid: False)
    monkeypatch.setattr(
        fetch_ids.ai,
        "seed_records",
        lambda path, **kw: iter(
            [
                {"arxiv_id": "2608.31115", "title": "Revised twice", "version": "v2"},
                {"arxiv_id": "2608.31116", "title": "Never mirrored", "version": "v1"},
            ]
        ),
    )
    monkeypatch.setattr(fetch_ids.ai, "thread_session", lambda: object())
    monkeypatch.setattr(fetch_ids.ai, "upsert_paper", lambda conn, rec: stored.append(rec))

    def month_objects(session, yymm):
        listings.append(yymm)
        return iter([("2608.31115", 1, 1024)])

    monkeypatch.setattr(fetch_ids.ai, "gcs_month_objects", month_objects)

    def download_pdf(session, arxiv_id, url):
        return pdf if url.endswith("2608.31115v1.pdf") else None

    monkeypatch.setattr(fetch_ids.ai, "download_pdf", download_pdf)

    assert fetch_ids.fetch(["2608.31115", "2608.31116"], concurrency=2, dry_run=False) == 0

    assert [(rec["arxiv_id"], rec["version"]) for rec in stored] == [("2608.31115", "v1")]
    # One listing for the month, however many ids missed in it.
    assert listings == ["2608"]
    err = capsys.readouterr().err
    assert "no PDF on the mirror for 2608.31116" in err
