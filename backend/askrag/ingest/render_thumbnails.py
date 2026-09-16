"""corpus/pdfs/** -> corpus/thumbs/{arxiv_id}.jpg — the card image for /papers.

Two sources, in order: the first image placed large enough on a page to be a
figure rather than a logo, else the top half of page one, which is the title
block and still reads as a paper.

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

    Vector figures carry no image object at all and are invisible here; those
    papers fall back to the page crop, which is why the fallback is not an
    error path.
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


def render_one(pdf: Path, out: Path, settings: Settings) -> Thumbnail:
    """Render one paper's thumbnail, writing `out`. Raises if the PDF will not open."""
    with pymupdf.open(pdf) as doc:
        if doc.page_count == 0:
            raise ValueError(f"{pdf.name} has no pages")
        found = _figure_clip(doc, settings)
        if found is not None:
            page, clip = found
            source = "figure"
        else:
            page = doc[0]
            rect = page.rect
            clip = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height / 2)
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
