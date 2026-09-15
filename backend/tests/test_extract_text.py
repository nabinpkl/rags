"""Tests for askrag.ingest.extract_text — fixture PDFs authored in-test, no corpus."""

import os

import pymupdf

from askrag.ingest.extract_text import run, text_path


def make_pdf(path, pages):
    """Author a PDF with one line of text per page."""
    doc = pymupdf.open()
    for line in pages:
        page = doc.new_page()
        page.insert_text((72, 90), line, fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def test_text_lands_under_its_id_month_with_form_feeds_between_pages(tmp_path):
    # The id-month, not the collector's {YYYY}/{MM} directory: that is what
    # the citation graph and the coverage census group by.
    make_pdf(tmp_path / "pdfs/2026/08/2608.00019.pdf", ["first page", "second page"])

    stats = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=2)

    written = tmp_path / "text/2608/2608.00019.txt"
    assert stats.written == 1 and stats.failed == 0
    text = written.read_text(encoding="utf-8")
    assert "first page" in text and "second page" in text
    # A form feed, never a bare newline: the citation regex tolerates a line
    # break inside an "arXiv:<id>" reference, so a newline separator would let
    # a page boundary forge one out of two unrelated fragments.
    assert "\f" in text


def test_a_current_text_file_is_left_alone_and_a_stale_one_is_rewritten(tmp_path):
    # This is what makes a month top-up cost only the new papers.
    pdf = make_pdf(tmp_path / "pdfs/2026/08/2608.00019.pdf", ["first page"])
    run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=1)
    dest = tmp_path / "text/2608/2608.00019.txt"
    dest.write_text("stale but current", encoding="utf-8")

    again = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=1)

    assert again.resumed == 1 and again.written == 0
    assert dest.read_text(encoding="utf-8") == "stale but current"

    # Re-collecting the paper (a new version) makes the PDF newer than the text.
    os.utime(pdf, (dest.stat().st_mtime + 10, dest.stat().st_mtime + 10))
    third = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=1)

    assert third.written == 1
    assert "first page" in dest.read_text(encoding="utf-8")


def test_an_id_with_no_id_month_is_skipped_rather_than_guessed_at(tmp_path):
    # Old-style ids (hep-th/9901001) are stored under pdfs/misc and have no
    # id-month; there is no correct folder for them in the text tree.
    make_pdf(tmp_path / "pdfs/misc/hep-th_9901001.pdf", ["first page"])

    stats = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=1)

    assert stats.total == 0 and stats.written == 0
    assert text_path(tmp_path / "text", "hep-th/9901001") is None


def test_one_unreadable_pdf_is_counted_and_the_rest_of_the_run_continues(tmp_path):
    make_pdf(tmp_path / "pdfs/2026/08/2608.00019.pdf", ["first page"])
    broken = tmp_path / "pdfs/2026/08/2608.00020.pdf"
    broken.write_bytes(b"%PDF-1.7 not really a pdf")

    stats = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=2)

    assert stats.written == 1 and stats.failed == 1
    assert (tmp_path / "text/2608/2608.00019.txt").exists()
    assert not (tmp_path / "text/2608/2608.00020.txt").exists()


def test_months_scope_the_run_so_a_top_up_cannot_widen_the_corpus(tmp_path):
    # The PDF store holds months the text tree deliberately does not. Pulling
    # them in would add their references to the citation graph, which is a
    # change to what every landing-page count means, not a bigger sample.
    make_pdf(tmp_path / "pdfs/2026/08/2608.00019.pdf", ["august"])
    make_pdf(tmp_path / "pdfs/2007/04/0704.00019.pdf", ["ancient"])

    stats = run(pdfs_dir=tmp_path / "pdfs", text_dir=tmp_path / "text", workers=1, months=["2608"])

    assert stats.total == 1 and stats.written == 1
    assert (tmp_path / "text/2608/2608.00019.txt").exists()
    assert not (tmp_path / "text/0704").exists()
