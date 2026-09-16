"""corpus/pdfs/** -> corpus/thumbs/{arxiv_id}.jpg — the card image for /papers.

Three sources, in order: an embedded image placed large enough on a page to
be a figure rather than a logo; a cluster of vector paths that is the same
shape, which is what most arXiv figures actually are; else the top half of
page one, which is the title block and still reads as a paper. Measured
2026-09-16 over 120 recent papers: 41% / 90% / the rest.

Whatever is chosen is then trimmed to the ink inside it. A page is roughly a
quarter margin by area, and at thumbnail size those margins are most of the
tile.

THE CACHE IS THE FILE. There is no manifest and no database column: a
thumbnail exists if its JPEG is on disk, and `thumbnail_for` renders one when
it is not. `routes_thumbnails.py` calls that on a cache miss, so a paper's
image appears the first time anyone looks at it and every later view is a
static file. This module's `run()` is the warmer that renders the backlog in
bulk; it is an optimisation, never a prerequisite. The consequence that made
it worth doing this way: a new month of papers is visible with pictures the
moment its PDFs land, with no reindex and no two-hour batch in between.

WE RENDER, WE NEVER FETCH. The image comes from the PDF we already hold.
Nothing here or downstream may reach arxiv.org to build a card — thirty cards
would be thirty requests per render, which is a scraper from arXiv's side.
See CLAUDE.md's hard constraints.

Fair use is what permits the image for the 36,560 papers under arXiv's
default licence, and it is the LOW-RESOLUTION crop beside a link back to the
source that qualifies — Kelly v. Arriba Soft (9th Cir. 2003), Perfect 10 v.
Amazon.com (9th Cir. 2007). `thumbnail_width` is therefore a compliance
setting as much as a layout one; raising it toward a readable page is the
change that would break the argument. The CC licences grant the crop
outright, on conditions the CARD carries rather than this file:

  - The card links to arxiv.org for the paper itself, version-pinned, and we
    never host the download (catalog-results.tsx).
  - A CC paper's card names and links its licence beside the attribution it
    already carries (lib/license-label.ts).
  - askRAG is non-commercial. Roughly 5,200 papers are NC-licensed, and ads,
    a paid tier or an enterprise plan would put their crops out of licence.
    That is D19's first revisit trigger, not a thing this file can check.
"""

import argparse
import logging
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from askrag import telemetry
from askrag.config import Settings, get_settings

_log = logging.getLogger("askrag.ingest.render_thumbnails")


@dataclass(frozen=True)
class Thumbnail:
    """One rendered image and what it was cropped from."""

    path: Path
    # "figure" or "page". Reported because it is the one number that says
    # whether the heuristic is finding real figures or quietly falling back
    # for everything, which a coverage count alone would hide.
    source: str
    width: int
    height: int


@dataclass
class RenderStats:
    considered: int = 0
    cached: int = 0
    missing_pdf: int = 0
    failed: int = 0
    from_figure: int = 0
    from_page: int = 0

    @property
    def rendered(self) -> int:
        return self.from_figure + self.from_page


def thumb_path(thumbs_dir: Path, arxiv_id: str) -> Path:
    """Flat, one file per paper. The URL is `/thumbs/{arxiv_id}.jpg`, so no
    caller anywhere has to know a sharding rule to build it."""
    return thumbs_dir / f"{arxiv_id}.jpg"


def pdf_path(pdfs_dir: Path, arxiv_id: str) -> Path:
    """The collector's {YYYY}/{MM}/ tree, which this module only ever reads."""
    return pdfs_dir / f"20{arxiv_id[:2]}" / arxiv_id[2:4] / f"{arxiv_id}.pdf"


def _figure_clip(
    doc: pymupdf.Document, settings: Settings
) -> tuple[pymupdf.Page, pymupdf.Rect] | None:
    """The first placed image big enough to be a figure rather than a logo.

    Measured on the page, not in the image's own pixels: a 2000px logo
    placed at 20pt is a logo. The thresholds are a floor in points plus a
    share of the page, so a wide-but-flat rule and a small inline glyph both
    fall out, and a half-column plot does not.

    Vector figures carry no image object at all and are invisible here —
    `_drawn_clip` is what finds those.
    """
    for number in range(min(settings.thumbnail_scan_pages, doc.page_count)):
        page = doc[number]
        page_area = abs(page.rect.width * page.rect.height)
        if page_area <= 0:
            continue
        for info in page.get_image_info(xrefs=True):
            rect = pymupdf.Rect(info["bbox"])
            if (
                rect.width >= settings.thumbnail_min_figure_width_pt
                and rect.height >= settings.thumbnail_min_figure_height_pt
                and (rect.width * rect.height) / page_area
                >= settings.thumbnail_min_figure_page_fraction
            ):
                return page, rect
    return None


def _drawings(page: pymupdf.Page, settings: Settings) -> list[pymupdf.Rect]:
    """The page's vector paths, grouped into the drawings they belong to.

    A plot is hundreds of separate strokes, so the paths have to be put back
    together before any of them looks like a figure. Two paths join when
    their rects come within `thumbnail_cluster_gap_pt` of each other.

    Dropped before grouping: paths too small to see, and any hairline running
    most of the page width, which is a rule under a heading or a table row and
    would otherwise weld every cluster on the page into one.
    """
    gap = settings.thumbnail_cluster_gap_pt
    groups: list[pymupdf.Rect] = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.width < 3 and rect.height < 3:
            continue
        if rect.height < 3 and rect.width > page.rect.width * 0.6:
            continue
        merged = pymupdf.Rect(rect)
        near = pymupdf.Rect(rect.x0 - gap, rect.y0 - gap, rect.x1 + gap, rect.y1 + gap)
        for group in [g for g in groups if _overlaps(near, g)]:
            merged = _union(merged, group)
            groups.remove(group)
        groups.append(merged)
    return groups


# A straight stroke — an axis, a grid line, a table rule — has a bbox with
# zero width or zero height, and PyMuPDF calls such a rect EMPTY. Both of its
# own combinators then quietly do the wrong thing: `intersects` answers False
# and `|=` is a no-op. So the two operations this grouping needs are spelled
# out, or the most common strokes in a plot never join anything.


def _overlaps(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
    return a.x0 <= b.x1 and b.x0 <= a.x1 and a.y0 <= b.y1 and b.y0 <= a.y1


def _union(a: pymupdf.Rect, b: pymupdf.Rect) -> pymupdf.Rect:
    return pymupdf.Rect(min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))


def _drawn_clip(
    doc: pymupdf.Document, settings: Settings
) -> tuple[pymupdf.Page, pymupdf.Rect] | None:
    """The largest drawing that is figure-shaped, for papers whose figures are
    vector art rather than embedded images.

    This is most of them. Measured 2026-09-16 over 120 recent papers: raster
    images alone found a figure for 41%, and adding this took it to 90%.

    The ceiling matters as much as the floor. Without one, the winner is
    routinely the union of a page's table rules or a boxed author block — a
    whole page of dense text, picked because it had the largest area.
    """
    for number in range(min(settings.thumbnail_scan_pages, doc.page_count)):
        page = doc[number]
        page_area = abs(page.rect.width * page.rect.height)
        if page_area <= 0:
            continue
        for rect in sorted(_drawings(page, settings), key=lambda r: -r.get_area()):
            share = rect.get_area() / page_area
            if (
                rect.width >= settings.thumbnail_min_figure_width_pt
                and rect.height >= settings.thumbnail_min_figure_height_pt
                and settings.thumbnail_min_figure_page_fraction
                <= share
                <= settings.thumbnail_max_figure_page_fraction
            ):
                return page, rect
    return None


def _trim(page: pymupdf.Page, clip: pymupdf.Rect, settings: Settings) -> pymupdf.Rect:
    """`clip` shrunk to the ink inside it.

    A letter page is roughly a quarter margin by area, and at 160px on a card
    those margins are most of the tile. Measured from pixels rather than from
    text and drawing boxes, because it has to be right for a figure's internal
    padding too, and a raster image's own white border is invisible to both.

    Greyscale, and small: the probe is only ever a few hundred rows, and the
    scan is a `min()` per row over a bytes slice. An all-white clip trims to
    nothing and is returned untouched.
    """
    probe_zoom = min(1.0, settings.thumbnail_trim_probe_px / max(clip.width, clip.height))
    probe = page.get_pixmap(
        matrix=pymupdf.Matrix(probe_zoom, probe_zoom),
        clip=clip,
        colorspace=pymupdf.csGRAY,
    )
    if probe.width == 0 or probe.height == 0:
        return clip
    ink = settings.thumbnail_trim_ink_level
    data, stride, width = probe.samples, probe.stride, probe.width
    rows = [y for y in range(probe.height) if min(data[y * stride : y * stride + width]) < ink]
    if not rows:
        return clip
    columns = [
        x
        for x in range(width)
        if min(data[y * stride + x] for y in range(probe.height)) < ink  # noqa: B905
    ]
    pad = settings.thumbnail_trim_padding_pt
    x_scale, y_scale = clip.width / width, clip.height / probe.height
    trimmed = pymupdf.Rect(
        clip.x0 + columns[0] * x_scale - pad,
        clip.y0 + rows[0] * y_scale - pad,
        clip.x0 + (columns[-1] + 1) * x_scale + pad,
        clip.y0 + (rows[-1] + 1) * y_scale + pad,
    )
    return trimmed & clip


def render_one(pdf: Path, out: Path, settings: Settings) -> Thumbnail:
    """Render one paper's thumbnail, writing `out`. Raises if the PDF will not open."""
    with pymupdf.open(pdf) as doc:
        if doc.page_count == 0:
            raise ValueError(f"{pdf.name} has no pages")
        found = _figure_clip(doc, settings) or _drawn_clip(doc, settings)
        if found is not None:
            page, clip = found
            clip = _trim(page, clip, settings)
            source = "figure"
        else:
            page = doc[0]
            # Trim FIRST, then halve: half of the page is half a page of
            # margin, and the title block sits in the top half of the CONTENT.
            content = _trim(page, page.rect, settings)
            clip = pymupdf.Rect(content.x0, content.y0, content.x1, content.y0 + content.height / 2)
            source = "page"
        zoom = settings.thumbnail_width / clip.width
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
        out.parent.mkdir(parents=True, exist_ok=True)
        # Written through a temp name and renamed: the warmer and a request
        # that missed the cache can render the same paper at the same moment,
        # and a reader must never be handed a half-written JPEG. Rename is
        # atomic within a filesystem, so the loser of that race overwrites
        # identical bytes.
        staging = out.with_suffix(f".{os.getpid()}.part")
        staging.write_bytes(pixmap.tobytes("jpeg", jpg_quality=settings.thumbnail_quality))
        staging.replace(out)
        return Thumbnail(path=out, source=source, width=pixmap.width, height=pixmap.height)


def thumbnail_for(
    arxiv_id: str, *, pdfs_dir: Path, thumbs_dir: Path, settings: Settings
) -> Path | None:
    """The paper's image, rendering it on first use. None if we hold no PDF.

    This is the whole cache protocol, shared by the request path and the
    warmer: look for the file, render it if absent, hand back the path.
    """
    out = thumb_path(thumbs_dir, arxiv_id)
    if out.exists():
        return out
    pdf = pdf_path(pdfs_dir, arxiv_id)
    if not pdf.exists():
        return None
    return render_one(pdf, out, settings).path


def run(
    *,
    pdfs_dir: Path,
    thumbs_dir: Path,
    settings: Settings,
    only: Iterable[str] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> RenderStats:
    """Render the backlog, skipping papers whose image is already cached."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = RenderStats()
    with tracer.start_as_current_span("askrag.ingest.render_thumbnails") as span:
        held = {path.stem for path in pdfs_dir.rglob("*.pdf")}
        if only is not None:
            held &= set(only)
        stats.considered = len(held)
        wanted = sorted(held)
        if limit is not None:
            wanted = wanted[:limit]

        for arxiv_id in wanted:
            out = thumb_path(thumbs_dir, arxiv_id)
            if out.exists() and not force:
                stats.cached += 1
                continue
            pdf = pdf_path(pdfs_dir, arxiv_id)
            if not pdf.exists():
                stats.missing_pdf += 1
                continue
            try:
                thumbnail = render_one(pdf, out, settings)
            except Exception as error:  # a corrupt PDF must not stop the run
                stats.failed += 1
                _log.warning("thumbnail failed for %s: %s", arxiv_id, error)
                continue
            if thumbnail.source == "figure":
                stats.from_figure += 1
            else:
                stats.from_page += 1

        span.set_attribute("askrag.thumbnails", stats.rendered)
        span.set_attribute("askrag.thumbnails_from_figure", stats.from_figure)
    _log.info(
        f"thumbnails: rendered {stats.rendered} of {stats.considered} papers "
        f"({stats.from_figure} figure, {stats.from_page} page top); "
        f"{stats.cached} already cached, {stats.missing_pdf} without a PDF, "
        f"{stats.failed} failed"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="render at most this many")
    parser.add_argument("--only", nargs="*", default=None, help="restrict to these arxiv ids")
    parser.add_argument("--force", action="store_true", help="re-render thumbnails that exist")
    args = parser.parse_args(argv)
    try:
        run(
            pdfs_dir=settings.pdfs_dir,
            thumbs_dir=settings.thumbs_dir,
            settings=settings,
            only=args.only,
            limit=args.limit,
            force=args.force,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
