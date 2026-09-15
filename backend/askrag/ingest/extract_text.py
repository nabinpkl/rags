"""corpus/pdfs/**/*.pdf -> corpus/text/{YYMM}/{arxiv_id}.txt — the flat text tree.

The citation graph is read from this tree (extract_citations.py), which is why
it exists beside extract_pdfs.py rather than inside it. The two extractions
have opposite shapes: this one is cheap and WIDE (every collected paper, plain
text, no layout), the other is expensive and NARROW (the few hundred papers the
landing page indexes, structured markdown with a page map for the chunker).
Running the narrow one over the whole PDF tree to get citations out of it was
measured at hours per ten thousand papers; this is minutes.

Old-style ids (hep-th/9901001) are not collected post-D18 and have no id-month,
so PDFs outside the {YYYY}/{MM} layout are skipped rather than guessed at.

Incremental by mtime: a paper whose .txt is newer than its .pdf is left alone,
so a run after a month top-up costs only the new papers.
"""

import argparse
import concurrent.futures as cf
import logging
import re
import sys
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from askrag.config import get_settings

_log = logging.getLogger("askrag.ingest.extract_text")

# The collector stores pdfs/{YYYY}/{MM}/{id}.pdf; the text tree keys on the
# id-month ({YYMM}), which is what the citation graph and the coverage census
# group by.
_NEW_STYLE_ID = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}$")
_PROGRESS_EVERY = 500


@dataclass
class RunStats:
    total: int = 0
    written: int = 0
    resumed: int = 0
    failed: int = 0


def text_path(text_dir: Path, arxiv_id: str) -> Path | None:
    """Where `arxiv_id`'s flat text belongs, or None if the id has no id-month."""
    match = _NEW_STYLE_ID.match(arxiv_id)
    if not match:
        return None
    return text_dir / f"{match.group(1)}{match.group(2)}" / f"{arxiv_id}.txt"


def pdf_text(pdf_path: Path) -> str:
    """Every page's text, in reading order, pages separated by a form feed.

    The form feed is what the tree already holds (verified byte-for-byte
    against the July and August text on disk), and it matters: the citation
    regex tolerates a line break inside "arXiv:" + id, so a separator that
    looked like an ordinary newline would let a page boundary forge one.
    """
    with pymupdf.open(pdf_path) as doc:
        return "\f".join(page.get_text() for page in doc)


def _extract_one(job: tuple[Path, Path]) -> tuple[Path, str | None]:
    """Worker: returns (destination, error message or None)."""
    pdf_path, dest = job
    try:
        text = pdf_text(pdf_path)
    except Exception as exc:  # noqa: BLE001 - pymupdf raises across its C surface
        return dest, f"{type(exc).__name__}: {exc}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Written through a temp file so an interrupted run never leaves a
    # half-file that the next run's mtime check would accept as current.
    tmp = dest.with_suffix(".txt.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)
    return dest, None


def _is_current(dest: Path, pdf_path: Path) -> bool:
    return dest.exists() and dest.stat().st_mtime >= pdf_path.stat().st_mtime


def run(
    pdfs_dir: Path, text_dir: Path, workers: int, months: Collection[str] | None = None
) -> RunStats:
    """Extract every PDF that has no current text file. Returns run counts.

    `months` restricts the run to id-months ("2608"). Scope is not an
    optimisation here: the PDF store holds ~43k papers the text tree
    deliberately does not, a thin sample of every month back to 2007 that was
    collected for facet work. Extracting all of it would put their references
    into the citation graph and silently change what every count on the
    landing page means, so a month top-up names its months.
    """
    if not pdfs_dir.is_dir():
        raise FileNotFoundError(f"no PDF tree at {pdfs_dir}")

    wanted = set(months) if months is not None else None
    jobs: list[tuple[Path, Path]] = []
    stats = RunStats()
    for pdf_path in sorted(pdfs_dir.rglob("*.pdf")):
        dest = text_path(text_dir, pdf_path.stem)
        if dest is None:
            continue
        if wanted is not None and dest.parent.name not in wanted:
            continue
        stats.total += 1
        if _is_current(dest, pdf_path):
            stats.resumed += 1
        else:
            jobs.append((pdf_path, dest))

    _log.info("%d pdfs, %d already current, %d to extract", stats.total, stats.resumed, len(jobs))
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for done, (dest, error) in enumerate(pool.map(_extract_one, jobs, chunksize=8), start=1):
            if error:
                stats.failed += 1
                # Loud: a paper missing from the text tree is a paper missing
                # from every citation count downstream.
                _log.warning("extraction failed for %s: %s", dest.stem, error)
            else:
                stats.written += 1
            if done % _PROGRESS_EVERY == 0:
                _log.info("%d/%d", done, len(jobs))
    return stats


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--workers", type=int, default=settings.extract_workers)
    parser.add_argument(
        "--months",
        nargs="+",
        metavar="YYMM",
        help="restrict the run to these id-months, e.g. --months 2608 2609",
    )
    args = parser.parse_args(argv)

    stats = run(
        pdfs_dir=settings.pdfs_dir,
        text_dir=settings.text_dir,
        workers=args.workers,
        months=args.months,
    )
    print(
        f"{stats.total} pdfs: {stats.written} extracted, "
        f"{stats.resumed} already current, {stats.failed} failed",
        file=sys.stderr,
    )
    return 1 if stats.failed and not stats.written else 0


if __name__ == "__main__":
    raise SystemExit(main())
