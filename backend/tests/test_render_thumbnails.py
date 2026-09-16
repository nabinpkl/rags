"""render_thumbnails: who gets a card image, and what it is a picture of."""

import json
import zipfile

import pymupdf
import pytest

from askrag.config import Settings
from askrag.ingest import render_thumbnails
from askrag.ingest.render_thumbnails import may_redistribute, read_manifest, run

CC_BY = "http://creativecommons.org/licenses/by/4.0/"
ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
CC_ND = "http://creativecommons.org/licenses/by-nc-nd/4.0/"


def _pdf(path, *, figure=None, title="A Paper About Something"):
    """A one-page PDF with a title, optionally carrying one placed image.

    `figure` is a (width, height) in points; a logo is just a small one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 96), title, fontsize=18)
    if figure is not None:
        width, height = figure
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 300))
        pixmap.set_rect(pixmap.irect, (40, 90, 160))
        page.insert_image(pymupdf.Rect(72, 300, 72 + width, 300 + height), pixmap=pixmap)
    doc.save(path)
    doc.close()


@pytest.fixture
def corpus(tmp_path):
    """Four papers: CC-BY with a figure, CC-BY without, arXiv-default, CC-ND."""
    pdfs = tmp_path / "pdfs"
    _pdf(pdfs / "2026" / "08" / "2608.00001.pdf", figure=(300, 200))
    _pdf(pdfs / "2026" / "08" / "2608.00002.pdf")
    _pdf(pdfs / "2026" / "08" / "2608.00003.pdf", figure=(300, 200))
    _pdf(pdfs / "2026" / "08" / "2608.00004.pdf", figure=(300, 200))

    seed = tmp_path / "archive.zip"
    records = [
        {"id": "2608.00001", "license": CC_BY},
        {"id": "2608.00002", "license": CC_BY},
        {"id": "2608.00003", "license": ARXIV_DEFAULT},
        {"id": "2608.00004", "license": CC_ND},
    ]
    with zipfile.ZipFile(seed, "w") as archive:
        archive.writestr(
            "arxiv-metadata-oai-snapshot.json",
            "\n".join(json.dumps(record) for record in records),
        )

    return {
        "pdfs": pdfs,
        "seed": seed,
        "thumbs": tmp_path / "thumbs",
        "manifest": tmp_path / "thumbnails.jsonl",
        "settings": Settings(corpus_dir=tmp_path, _env_file=None),  # ty: ignore[unknown-argument]
    }


def _run(corpus, **overrides):
    return run(
        pdfs_dir=corpus["pdfs"],
        seed_zip=corpus["seed"],
        thumbs_dir=corpus["thumbs"],
        manifest_path=corpus["manifest"],
        settings=corpus["settings"],
        **overrides,
    )


def test_only_a_licence_that_allows_redistribution_gets_a_thumbnail(corpus):
    """§6b: a thumbnail is a crop of an e-print, served from our servers.

    arXiv's default licence grants arXiv the right to distribute and grants
    us nothing; NoDerivatives forbids the crop itself. Neither may have a
    file on disk, which is a stronger check than "the API returns null".
    """
    stats = _run(corpus)

    written = {path.stem for path in corpus["thumbs"].rglob("*.jpg")}
    assert written == {"2608.00001", "2608.00002"}
    assert stats.skipped_licence == 2
    assert set(read_manifest(corpus["manifest"])) == written


def test_the_licence_gate_reads_the_terms_not_the_host():
    assert may_redistribute(CC_BY)
    assert may_redistribute("https://creativecommons.org/licenses/by-sa/4.0/")
    assert may_redistribute("http://creativecommons.org/publicdomain/zero/1.0/")
    assert not may_redistribute(ARXIV_DEFAULT)
    assert not may_redistribute(CC_ND)
    assert not may_redistribute(None)
    assert not may_redistribute("")


def test_a_paper_with_a_figure_is_cropped_to_it_and_one_without_is_not(corpus):
    _run(corpus)
    manifest = read_manifest(corpus["manifest"])

    assert manifest["2608.00001"].source == "figure"
    assert manifest["2608.00002"].source == "page"


def test_a_logo_is_not_a_figure(corpus):
    """The heuristic measures where an image is PLACED, so a 400x300 pixmap
    dropped in at 40x30 points is a logo and must not become the thumbnail."""
    _pdf(corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf", figure=(40, 30))

    _run(corpus)

    assert read_manifest(corpus["manifest"])["2608.00002"].source == "page"


def test_the_image_is_rendered_at_the_configured_width(corpus):
    _run(corpus)
    manifest = read_manifest(corpus["manifest"])

    assert manifest["2608.00001"].width == pytest.approx(corpus["settings"].thumbnail_width, abs=2)
    # Read back as pixels, which is what the browser gets: MuPDF opening a
    # JPEG as a document reports its rect in points at 96 DPI instead.
    written = pymupdf.Pixmap(str(corpus["thumbs"] / manifest["2608.00001"].path))
    assert written.width == manifest["2608.00001"].width
    assert written.height == manifest["2608.00001"].height


def test_a_rerun_carries_the_manifest_forward_rather_than_re_rendering(corpus, monkeypatch):
    _run(corpus)
    before = read_manifest(corpus["manifest"])

    def refuse(*args, **kwargs):
        raise AssertionError("re-rendered a thumbnail that was already on disk")

    monkeypatch.setattr(render_thumbnails, "render_one", refuse)
    _run(corpus)

    # Same entries AND the same sources: a rerun that guessed would report
    # every thumbnail as a page crop and silently erase the figure count.
    assert read_manifest(corpus["manifest"]) == before


def test_a_corrupt_pdf_is_counted_and_does_not_stop_the_run(corpus):
    (corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf").write_bytes(b"not a pdf")

    stats = _run(corpus)

    assert stats.failed == 1
    assert stats.rendered == 1
    assert set(read_manifest(corpus["manifest"])) == {"2608.00001"}
