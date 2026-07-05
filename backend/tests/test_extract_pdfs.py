"""Tests for askrag.ingest.extract_pdfs — fixture PDFs authored in-test, no corpus."""

import json
import os

import pymupdf
import pytest

from askrag.ingest import extract_pdfs

BODY = "Retrieval augmented generation over arxiv papers. "


def make_pdf(path, headings, body_pages_after=0):
    """Author a PDF with one large-font heading per page (pymupdf4llm sees h1)."""
    doc = pymupdf.open()
    for heading in headings:
        page = doc.new_page()
        if heading is not None:
            page.insert_text((72, 90), heading, fontsize=16)
        for k in range(6):
            page.insert_text((72, 130 + 14 * k), BODY * 2, fontsize=10)
    for _ in range(body_pages_after):
        page = doc.new_page()
        for k in range(6):
            page.insert_text((72, 130 + 14 * k), BODY * 2, fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def corpus(tmp_path):
    return {
        "pdfs": tmp_path / "pdfs",
        "extracted": tmp_path / "extracted",
        "skiplist": tmp_path / "skiplist.json",
    }


def run(corpus, **kwargs):
    kwargs.setdefault("workers", 1)
    return extract_pdfs.run(
        pdfs_dir=corpus["pdfs"],
        extracted_dir=corpus["extracted"],
        skiplist_path=corpus["skiplist"],
        **kwargs,
    )


# --- extract_one: the frozen schema ----------------------------------------


def test_clean_title_strips_emphasis_only():
    # Real corpus headings arrive as "**1 Introduction**"; body markdown is
    # untouched, only the section-title metadata is normalized.
    assert extract_pdfs._clean_title("**1 Introduction**") == "1 Introduction"
    assert extract_pdfs._clean_title("_Abstract_ ") == "Abstract"
    assert extract_pdfs._clean_title("2 Related Work") == "2 Related Work"
    # Bold runs split mid-title by pymupdf4llm; single underscores stay
    # (they can be content, e.g. variable names).
    assert extract_pdfs._clean_title("2.1 Simplification for** **_m_ scales") == (
        "2.1 Simplification for _m_ scales"
    )
    # Inline HTML let through by pymupdf4llm (real corpus: 2009.08859).
    assert extract_pdfs._clean_title("Zero <u>(PC5)</u>") == "Zero (PC5)"
    assert extract_pdfs._clean_title("**Kevin Buchin**<sup>1</sup>") == "Kevin Buchin1"


def test_page_map_tiles_the_markdown(tmp_path):
    pdf = make_pdf(tmp_path / "2606.99999.pdf", ["1 One", "2 Two", "3 Three"])
    payload = extract_pdfs.extract_one(pdf)
    pages = payload["pages"]
    # 1-based, one entry per page, contiguous half-open spans that tile the
    # markdown exactly — the chunker maps any char range to a page (D6/D7).
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert pages[0]["char_start"] == 0
    assert all(a["char_end"] == b["char_start"] for a, b in zip(pages, pages[1:], strict=False))
    assert pages[-1]["char_end"] == len(payload["markdown"])
    # Spans slice back to per-page content: page 2's heading lives inside
    # page 2's span and nowhere else.
    md = payload["markdown"]
    assert "2 Two" in md[pages[1]["char_start"] : pages[1]["char_end"]]
    assert "2 Two" not in md[pages[0]["char_start"] : pages[0]["char_end"]]


def test_sections_and_page_anchors(tmp_path):
    pdf = make_pdf(
        tmp_path / "2606.11111.pdf",
        ["1 Introduction", "2 Methods", "3 Results"],
        body_pages_after=1,
    )
    payload = extract_pdfs.extract_one(pdf)
    assert set(payload) == {"markdown", "sections", "pages", "n_pages"}
    assert payload["n_pages"] == 4
    assert BODY.strip() in payload["markdown"]
    titles = [s["title"] for s in payload["sections"]]
    assert titles == ["1 Introduction", "2 Methods", "3 Results"]
    # 1-based inclusive; a section runs to the next section's start page,
    # the last one to the end of the document.
    assert [(s["page_start"], s["page_end"]) for s in payload["sections"]] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]


def test_headerless_pdf_gets_whole_document_section(tmp_path):
    pdf = make_pdf(tmp_path / "2606.22222.pdf", [None, None])
    payload = extract_pdfs.extract_one(pdf)
    assert payload["sections"] == [{"title": "", "page_start": 1, "page_end": 2}]


def test_front_matter_before_first_heading_is_covered(tmp_path):
    pdf = make_pdf(tmp_path / "2606.33333.pdf", [None, "1 Introduction"])
    payload = extract_pdfs.extract_one(pdf)
    assert payload["sections"][0] == {"title": "", "page_start": 1, "page_end": 2}
    assert payload["sections"][1]["title"] == "1 Introduction"
    # Full page coverage: every page falls inside some section.
    assert payload["sections"][-1]["page_end"] == payload["n_pages"]


def test_encrypted_pdf_raises_skip(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 90), "secret", fontsize=10)
    path = tmp_path / "2606.44444.pdf"
    # Constant exists at runtime; pymupdf's stubs don't declare it.
    aes256 = pymupdf.PDF_ENCRYPT_AES_256  # pyright: ignore[reportAttributeAccessIssue]
    doc.save(path, encryption=aes256, user_pw="pw")
    doc.close()
    with pytest.raises(extract_pdfs.ExtractionSkip, match="encrypted"):
        extract_pdfs.extract_one(path)


# --- run(): skiplist, resume, retry -----------------------------------------


def test_corrupt_pdf_lands_in_skiplist_not_a_crash(corpus):
    make_pdf(corpus["pdfs"] / "2606.55555.pdf", ["1 Fine"])
    bad = corpus["pdfs"] / "2606.66666.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated garbage")
    stats = run(corpus)
    assert stats == {
        "total": 2,
        "resumed": 0,
        "skiplisted_prior": 0,
        "extracted": 1,
        "skiplisted_new": 1,
    }
    assert (corpus["extracted"] / "2606.55555.json").exists()
    assert not (corpus["extracted"] / "2606.66666.json").exists()
    skiplist = json.loads(corpus["skiplist"].read_text())
    entry = skiplist["2606.66666"]
    assert entry["reason"] and entry["pdf"].endswith("2606.66666.pdf") and entry["failed_at"]


def test_resume_skips_current_and_redoes_stale(corpus):
    pdf = make_pdf(corpus["pdfs"] / "2606.77777.pdf", ["1 Intro"])
    assert run(corpus)["extracted"] == 1
    stats = run(corpus)
    assert (stats["resumed"], stats["extracted"]) == (1, 0)
    # PDF newer than its extraction -> re-extract.
    out = corpus["extracted"] / "2606.77777.json"
    os.utime(pdf, (pdf.stat().st_atime, out.stat().st_mtime + 10))
    stats = run(corpus)
    assert (stats["resumed"], stats["extracted"]) == (0, 1)


def test_skiplisted_pdfs_retry_only_on_flag(corpus):
    bad = corpus["pdfs"] / "2606.88888.pdf"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not a pdf at all")
    assert run(corpus)["skiplisted_new"] == 1
    assert run(corpus)["skiplisted_prior"] == 1  # not re-ground by default
    # Fixed file + --retry-skipped -> extracted and dropped from the skiplist.
    make_pdf(bad, ["1 Fixed"])
    stats = run(corpus, retry_skipped=True)
    assert stats["extracted"] == 1
    assert json.loads(corpus["skiplist"].read_text()) == {}


def test_limit_takes_even_stride(corpus):
    for i in range(10):
        make_pdf(corpus["pdfs"] / f"26{i:02d}" / f"26{i:02d}.00001.pdf", ["1 A"])
    stats = run(corpus, limit=3)
    assert stats["total"] == 3
    extracted = sorted(p.stem for p in corpus["extracted"].glob("*.json"))
    assert extracted == ["2600.00001", "2603.00001", "2606.00001"]
