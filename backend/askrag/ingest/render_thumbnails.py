"""corpus/pdfs/** -> corpus/thumbs/{YYYY}/{MM}/{arxiv_id}.jpg + corpus/thumbnails.jsonl.

One small image per paper, for the card that names it on /papers. Two
sources, in order: the first figure large enough to be a figure, else the
top half of page one, which is the title block and reads as a paper even
when it is not a picture.

WHO GETS ONE IS A LICENCE QUESTION, not a rendering one. §6b rule 3 is
flat — never serve an e-print from our servers — and a crop of a page is a
piece of one. arXiv's default licence (nonexclusive-distrib) grants arXiv
the right to distribute the e-print and grants us nothing, so those papers
get no thumbnail and keep the category glyph. Creative Commons BY, BY-SA,
BY-NC-SA and the public-domain dedications do grant it, with attribution
the card already carries (title, authors, a link to the version-pinned
arXiv page). ND is excluded with the default licence: a crop is a
derivative work, and "NoDerivatives" says no.

The manifest is this stage's only output to the rest of the pipeline;
build_indexes reads it into `papers.thumbnail` and nothing else looks at
the files except Caddy, which serves them as static bytes.
"""

import argparse
import json
import logging
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from askrag import telemetry
from askrag.config import Settings, get_settings
from askrag.ingest import kaggle_seed

_log = logging.getLogger("askrag.ingest.render_thumbnails")

# Licence URLs whose terms allow us to redistribute a crop with attribution.
# Matched as a prefix on the recorded URL so the 3.0 and 4.0 vintages of each
# are covered by one entry; see the module docstring for what is deliberately
# absent (nonexclusive-distrib, and every -nd- variant).
REDISTRIBUTABLE = (
    "http://creativecommons.org/licenses/by/",
    "http://creativecommons.org/licenses/by-sa/",
    "http://creativecommons.org/licenses/by-nc-sa/",
    "http://creativecommons.org/publicdomain/zero/",
    "http://creativecommons.org/licenses/publicdomain",
)


def may_redistribute(license_url: str | None) -> bool:
    """Does this paper's licence let us serve a crop of it from our servers?"""
    if not license_url:
        return False
    normalized = license_url.replace("https://", "http://")
    return normalized.startswith(REDISTRIBUTABLE)


@dataclass(frozen=True)
class Thumbnail:
    """One rendered image, as the manifest records it."""

    arxiv_id: str
    # Relative to the thumbs dir, which is also the path Caddy serves it at.
    path: str
    # "figure" or "page". Kept because it is the one number that says whether
    # the heuristic is finding real figures or quietly falling back for
    # everything, which a coverage count alone would hide.
    source: str
    width: int
    height: int


@dataclass
class RenderStats:
    considered: int = 0
    skipped_licence: int = 0
    skipped_missing_pdf: int = 0
    failed: int = 0
    from_figure: int = 0
    from_page: int = 0

    @property
    def rendered(self) -> int:
        return self.from_figure + self.from_page


def relative_path(arxiv_id: str) -> str:
    """`2608.00380` -> `2026/08/2608.00380.jpg`, mirroring corpus/pdfs."""
    return f"20{arxiv_id[:2]}/{arxiv_id[2:4]}/{arxiv_id}.jpg"


def pdf_path(pdfs_dir: Path, arxiv_id: str) -> Path:
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
        # Written through a temp name: a half-written JPEG is a broken image
        # on a card, and Caddy serves whatever is on disk with no validation.
        staging = out.with_suffix(".jpg.part")
        staging.write_bytes(pixmap.tobytes("jpeg", jpg_quality=settings.thumbnail_quality))
        staging.replace(out)
        return Thumbnail(
            arxiv_id=pdf.stem,
            path=relative_path(pdf.stem),
            source=source,
            width=pixmap.width,
            height=pixmap.height,
        )


def _licensed_ids(seed_zip: Path, ids: set[str]) -> Iterator[str]:
    """The subset of `ids` whose seed licence permits redistribution."""
    for record in kaggle_seed.iter_records(seed_zip, ids):
        if may_redistribute(record.get("license")):
            yield record["id"]


def run(
    *,
    pdfs_dir: Path,
    seed_zip: Path,
    thumbs_dir: Path,
    manifest_path: Path,
    settings: Settings,
    only: Iterable[str] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> RenderStats:
    """Render every missing thumbnail and rewrite the manifest."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = RenderStats()
    with tracer.start_as_current_span("askrag.ingest.render_thumbnails") as span:
        held = {path.stem for path in pdfs_dir.rglob("*.pdf")}
        if only is not None:
            held &= set(only)
        stats.considered = len(held)
        previous = read_manifest(manifest_path)
        allowed = sorted(_licensed_ids(seed_zip, held))
        stats.skipped_licence = len(held) - len(allowed)
        if limit is not None:
            allowed = allowed[:limit]

        thumbnails: list[Thumbnail] = []
        for arxiv_id in allowed:
            out = thumbs_dir / relative_path(arxiv_id)
            pdf = pdf_path(pdfs_dir, arxiv_id)
            if not pdf.exists():
                stats.skipped_missing_pdf += 1
                continue
            done = previous.get(arxiv_id)
            if done is not None and out.exists() and not force:
                # Already rendered, and the previous manifest knows what it
                # was cropped from. Carrying the entry forward keeps a rerun
                # cheap without inventing a figure/page split it cannot see.
                thumbnails.append(done)
                continue
            try:
                thumbnail = render_one(pdf, out, settings)
            except Exception as error:  # a corrupt PDF must not stop the run
                stats.failed += 1
                _log.warning("thumbnail failed for %s: %s", arxiv_id, error)
                continue
            thumbnails.append(thumbnail)

        for thumbnail in thumbnails:
            if thumbnail.source == "figure":
                stats.from_figure += 1
            else:
                stats.from_page += 1

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        staging = manifest_path.with_suffix(".jsonl.part")
        staging.write_text(
            "".join(json.dumps(asdict(thumbnail)) + "\n" for thumbnail in thumbnails)
        )
        staging.replace(manifest_path)

        span.set_attribute("askrag.thumbnails", stats.rendered)
        span.set_attribute("askrag.thumbnails_from_figure", stats.from_figure)
    _log.info(
        f"thumbnails: {stats.rendered} of {stats.considered} papers "
        f"({stats.from_figure} figure, {stats.from_page} page top); "
        f"{stats.skipped_licence} skipped on licence, {stats.failed} failed"
    )
    return stats


def read_manifest(path: Path) -> dict[str, Thumbnail]:
    """The manifest as written last time, or empty. Absent is not an error:
    the first run has no previous manifest, and neither does a build that
    never rendered thumbnails at all."""
    if not path.exists():
        return {}
    entries = (json.loads(line) for line in path.read_text().splitlines() if line)
    return {entry["arxiv_id"]: Thumbnail(**entry) for entry in entries}


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
            seed_zip=settings.kaggle_seed_path,
            thumbs_dir=settings.thumbs_dir,
            manifest_path=settings.thumbnails_manifest_path,
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
