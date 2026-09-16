"""render_thumbnails: what each card's image is a picture of, and when."""

import pymupdf
import pytest

from askrag.config import Settings
from askrag.ingest import render_thumbnails
from askrag.ingest.render_thumbnails import render_one, run, thumb_path, thumbnail_for


def _pdf(path, *, figure=None, drawn=None, rules=0, title="A Paper About Something"):
    """A one-page PDF with a title, and optionally a picture.

    `figure` places a raster image at (width, height) in points; a logo is
    just a small one. `drawn` strokes a grid of short vector lines over that
    same box, which is what a plot actually is. `rules` draws that many
    full-width hairlines down the page — a table's rows, not a figure.
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
    if drawn is not None:
        width, height = drawn
        for step in range(0, int(width), 10):
            page.draw_line((72 + step, 300), (72 + step, 300 + height), width=0.7)
    for row in range(rules):
        y = 120 + row * 18
        page.draw_line((40, y), (page.rect.width - 40, y), width=0.5)
    doc.save(path)
    doc.close()


@pytest.fixture
def corpus(tmp_path):
    """Three papers: one with a real figure, one with none, one with a logo."""
    pdfs = tmp_path / "pdfs"
    _pdf(pdfs / "2026" / "08" / "2608.00001.pdf", figure=(300, 200))
    _pdf(pdfs / "2026" / "08" / "2608.00002.pdf")
    _pdf(pdfs / "2026" / "08" / "2608.00003.pdf", figure=(40, 30))

    return {
        "pdfs": pdfs,
        "thumbs": tmp_path / "thumbs",
        "settings": Settings(corpus_dir=tmp_path, _env_file=None),  # ty: ignore[unknown-argument]
    }


def _run(corpus, **overrides):
    return run(
        pdfs_dir=corpus["pdfs"],
        thumbs_dir=corpus["thumbs"],
        settings=corpus["settings"],
        **overrides,
    )


def _for(corpus, arxiv_id):
    return thumbnail_for(
        arxiv_id,
        pdfs_dir=corpus["pdfs"],
        thumbs_dir=corpus["thumbs"],
        settings=corpus["settings"],
    )


def _render(corpus, arxiv_id):
    return render_one(
        corpus["pdfs"] / "2026" / "08" / f"{arxiv_id}.pdf",
        thumb_path(corpus["thumbs"], arxiv_id),
        corpus["settings"],
    )


def test_a_thumbnail_is_rendered_on_first_use_and_found_on_the_next(corpus):
    """The cache IS the file: there is no manifest and no database column, so
    nothing has to run before a paper's card can show a picture."""
    assert _for(corpus, "2608.00001") == corpus["thumbs"] / "2608.00001.jpg"
    assert (corpus["thumbs"] / "2608.00001.jpg").exists()

    before = (corpus["thumbs"] / "2608.00001.jpg").stat().st_mtime_ns
    assert _for(corpus, "2608.00001").stat().st_mtime_ns == before


def test_a_paper_we_hold_no_pdf_for_has_no_thumbnail_and_no_error(corpus):
    assert _for(corpus, "2608.09999") is None


def test_the_warmer_renders_the_backlog_and_skips_what_is_cached(corpus):
    """`just thumbnails` is an optimisation over the on-demand path, never a
    prerequisite for it, so a second run must do no work."""
    first = _run(corpus)
    second = _run(corpus)

    assert first.rendered == 3
    assert {path.stem for path in corpus["thumbs"].glob("*.jpg")} == {
        "2608.00001",
        "2608.00002",
        "2608.00003",
    }
    assert second.rendered == 0
    assert second.cached == 3


def test_a_paper_with_a_figure_is_cropped_to_it_and_one_without_is_not(corpus):
    assert _render(corpus, "2608.00001").source == "figure"
    assert _render(corpus, "2608.00002").source == "page"


def test_a_logo_is_not_a_figure(corpus):
    """The heuristic measures where an image is PLACED, so a 400x300 pixmap
    dropped in at 40x30 points is a logo and must not become the thumbnail."""
    assert _render(corpus, "2608.00003").source == "page"


def test_the_image_stays_small_enough_to_be_a_thumbnail(corpus):
    """Low resolution is what makes the crop fair use for the 36,560 papers
    under arXiv's default licence (D19), so the width is a compliance setting
    and not only a layout one."""
    thumbnail = _render(corpus, "2608.00001")

    assert thumbnail.width == pytest.approx(corpus["settings"].thumbnail_width, abs=2)
    # Read back as pixels, which is what the browser gets: MuPDF opening a
    # JPEG as a document reports its rect in points at 96 DPI instead.
    written = pymupdf.Pixmap(str(thumbnail.path))
    assert written.width == thumbnail.width
    assert written.height == thumbnail.height


def test_a_corrupt_pdf_is_counted_and_does_not_stop_the_warmer(corpus):
    (corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf").write_bytes(b"not a pdf")

    stats = _run(corpus)

    assert stats.failed == 1
    assert stats.rendered == 2
    assert {path.stem for path in corpus["thumbs"].glob("*.jpg")} == {
        "2608.00001",
        "2608.00003",
    }


def test_nothing_is_left_half_written_for_a_reader_to_fetch(corpus, monkeypatch):
    """Caddy serves whatever is on disk with no validation, and the warmer
    and a cache-missing request can render the same paper at once. The file
    appears by rename, so a reader gets whole bytes or a 404, never half."""
    real = render_thumbnails.Path.write_bytes

    def crash_mid_write(self, data):
        real(self, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(render_thumbnails.Path, "write_bytes", crash_mid_write)
    with pytest.raises(OSError):
        _for(corpus, "2608.00001")

    assert not (corpus["thumbs"] / "2608.00001.jpg").exists()


def test_a_vector_plot_is_a_figure_even_though_it_is_not_an_image(corpus):
    """Most arXiv figures are vector art and carry no image object at all.
    Measured 2026-09-16 over 120 recent papers: raster alone found a figure
    for 41% of them, and grouping vector paths took it to 88%."""
    _pdf(corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf", drawn=(300, 200))

    assert _render(corpus, "2608.00002").source == "figure"


def test_a_page_of_table_rules_is_not_a_figure(corpus):
    """The ceiling on how much of a page a drawing may cover. Without it the
    winner is routinely the union of a table's rules or a boxed author list,
    which is a whole page of dense text picked for having the largest area."""
    _pdf(corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf", rules=30)

    assert _render(corpus, "2608.00002").source == "page"


def test_the_page_crop_is_the_top_of_the_CONTENT_not_of_the_paper(corpus):
    """A letter page is roughly a quarter margin by area, and at 160px on a
    card those margins are most of the tile. Half of the page would be half a
    page of margin; half of the content is the title block."""
    page_height = pymupdf.open(corpus["pdfs"] / "2026" / "08" / "2608.00002.pdf")[0].rect.height

    thumbnail = _render(corpus, "2608.00002")
    ratio = thumbnail.height / thumbnail.width

    # The fixture's ink is one line of title, so trimming leaves a wide, flat
    # box — nothing like the tall half-page an untrimmed crop would give.
    assert ratio < 0.5
    assert thumbnail.height < page_height


def test_an_empty_page_trims_to_nothing_and_is_left_alone(corpus):
    """A scanned blank or an all-white first page has no ink to find. The
    trim must return the clip it was given rather than an empty rect, which
    would divide by zero on the way to a zoom factor."""
    blank = corpus["pdfs"] / "2026" / "08" / "2608.00004.pdf"
    blank.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.new_page()
    doc.save(blank)
    doc.close()

    assert _for(corpus, "2608.00004") is not None
