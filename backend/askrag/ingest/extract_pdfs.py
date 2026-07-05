"""corpus/pdfs/** -> corpus/extracted/{arxiv_id}.json + corpus/skiplist.json (D6).

Per-paper output schema — a FROZEN interface, consumed verbatim by the
chunker (#12); changing its shape is spec-amendment territory:

    {"markdown": str,
     "sections": [{"title": str, "page_start": int, "page_end": int}],
     "pages": [{"page": int, "char_start": int, "char_end": int}],
     "n_pages": int}

Page numbers are 1-based, matching the PDF viewer's #page=N anchors (D9).
"pages" is D6's page map: char_start inclusive / char_end exclusive spans
into `markdown` that tile it exactly (page i+1 starts where page i ends;
the last char_end == len(markdown)), so the chunker can map any markdown
character range to its page(s) without re-parsing the PDF. Section ranges
are inclusive: content runs from a heading to the next heading, so adjacent
sections share their boundary page, and sections always cover pages
1..n_pages (an untitled preamble/whole-document section fills any gap).
Failures are recorded, never silently dropped: skiplist.json maps
arxiv_id -> {pdf, reason, failed_at}.
"""

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pymupdf
import pymupdf4llm

from askrag.config import get_settings

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_PROGRESS_EVERY = 100  # logging cadence (progress lines / skiplist flushes), not behavior


class ExtractionSkip(Exception):
    """Raised for PDFs that cannot be extracted; the message is the skiplist reason.

    Carries only its message so it survives pickling across the process pool.
    """


@dataclass(frozen=True)
class Section:
    title: str
    page_start: int  # 1-based, inclusive
    page_end: int


@dataclass(frozen=True)
class PageSpan:
    page: int  # 1-based
    char_start: int  # inclusive offset into Extraction.markdown
    char_end: int  # exclusive


@dataclass(frozen=True)
class Extraction:
    """The frozen cache payload; asdict() of this is the on-disk JSON schema."""

    markdown: str
    sections: list[Section]
    pages: list[PageSpan]
    n_pages: int


@dataclass(frozen=True)
class SkipEntry:
    """One skiplist.json record; asdict() of this is the on-disk entry shape."""

    pdf: str
    reason: str
    failed_at: str  # UTC ISO 8601


@dataclass
class RunStats:
    total: int = 0
    resumed: int = 0
    skiplisted_prior: int = 0
    extracted: int = 0
    skiplisted_new: int = 0


_TITLE_TAG_RE = re.compile(r"</?(?:u|i|b|sup|sub)>")


def _clean_title(raw: str) -> str:
    # pymupdf4llm renders bold headings as "# **Title**", often with the
    # bold run split mid-title ("for** **_m_ scales"), and lets inline HTML
    # through ("Zero <u>(PC5)</u>"). Titles are section metadata (navigation
    # anchors), not content, so bold markers and inline tags go everywhere
    # and other emphasis goes at the ends; the markdown body keeps every
    # marker.
    return _TITLE_TAG_RE.sub("", raw.replace("**", "")).strip().strip("*_").strip()


def extract_one(pdf_path: Path) -> Extraction:
    """One PDF -> the frozen cache payload. Raises ExtractionSkip with a reason."""
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ExtractionSkip("encrypted (needs password)")
        n_pages = doc.page_count
        if n_pages == 0:
            raise ExtractionSkip("zero pages")
        # page_chunks=True returns one dict per page; the annotation on
        # to_markdown is too loose for pyright to see that.
        pages = cast(list[dict], pymupdf4llm.to_markdown(doc, page_chunks=True))

    page_texts = [page["text"] for page in pages]
    markdown = "".join(page_texts)
    if not markdown.strip():
        raise ExtractionSkip("no extractable text (scanned image PDF?)")

    page_map: list[PageSpan] = []
    offset = 0
    for page_no, text in enumerate(page_texts, start=1):
        page_map.append(PageSpan(page=page_no, char_start=offset, char_end=offset + len(text)))
        offset += len(text)

    headings: list[tuple[int, str]] = []
    for page_no, text in enumerate(page_texts, start=1):
        for match in _HEADING_RE.finditer(text):
            headings.append((page_no, _clean_title(match.group(1))))

    sections: list[Section] = []
    if not headings or headings[0][0] > 1:
        # Front matter before the first detected heading (or a heading-free
        # document) still needs page anchors for the chunker.
        preamble_end = headings[0][0] if headings else n_pages
        sections.append(Section(title="", page_start=1, page_end=preamble_end))
    for i, (page_no, title) in enumerate(headings):
        page_end = headings[i + 1][0] if i + 1 < len(headings) else n_pages
        sections.append(Section(title=title, page_start=page_no, page_end=page_end))

    return Extraction(markdown=markdown, sections=sections, pages=page_map, n_pages=n_pages)


def _write_json_atomic(path: Path, payload: dict, indent: int | None = None) -> None:
    # A killed run must never leave a truncated JSON that a resume would
    # then trust; rename is atomic on POSIX.
    tmp = path.with_suffix(path.suffix + ".tmp")
    # encoding pinned: the full-corpus run may happen under a C/POSIX locale
    # (cron/ssh), where the preferred encoding is ASCII.
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def _extract_worker(pdf_path: Path, out_path: Path) -> None:
    """Pool worker. Raises ExtractionSkip (pickle-safe) for every failure mode;
    the pool re-raises it in the parent, which owns the skiplist."""
    try:
        payload = extract_one(pdf_path)
    except ExtractionSkip:
        raise
    except Exception as exc:
        # Corrupt files raise all over pymupdf's C surface; arbitrary
        # exceptions may not survive pickling back to the parent, a
        # message-only ExtractionSkip always does.
        raise ExtractionSkip(f"{type(exc).__name__}: {exc}") from exc
    _write_json_atomic(out_path, asdict(payload))


def _load_skiplist(path: Path) -> dict[str, SkipEntry]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {arxiv_id: SkipEntry(**entry) for arxiv_id, entry in raw.items()}


def _save_skiplist(path: Path, skiplist: dict[str, SkipEntry]) -> None:
    # Sorted + indented: the skiplist is a human-read artifact (issue #11
    # acceptance) and feeds ingest_stats (D12).
    ordered = {arxiv_id: asdict(entry) for arxiv_id, entry in sorted(skiplist.items())}
    _write_json_atomic(path, ordered, indent=2)


def _is_current(out_path: Path, pdf_path: Path) -> bool:
    return out_path.exists() and out_path.stat().st_mtime >= pdf_path.stat().st_mtime


def run(
    pdfs_dir: Path,
    extracted_dir: Path,
    skiplist_path: Path,
    workers: int,
    limit: int | None = None,
    retry_skipped: bool = False,
) -> RunStats:
    """Extract every PDF under pdfs_dir; returns counts for the run summary."""
    extracted_dir.mkdir(parents=True, exist_ok=True)
    skiplist = _load_skiplist(skiplist_path)

    all_pdfs = sorted(pdfs_dir.rglob("*.pdf"))
    if limit is not None and limit < len(all_pdfs):
        # Evenly strided sample: spans the year folders instead of the
        # oldest slice, so sample latency projects onto the full corpus.
        stride = len(all_pdfs) // limit
        all_pdfs = all_pdfs[::stride][:limit]

    stats = RunStats(total=len(all_pdfs))
    todo: list[Path] = []
    for pdf in all_pdfs:
        if _is_current(extracted_dir / f"{pdf.stem}.json", pdf):
            stats.resumed += 1
        elif pdf.stem in skiplist and not retry_skipped:
            stats.skiplisted_prior += 1
        else:
            todo.append(pdf)

    started = time.monotonic()
    done = 0
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_worker, pdf, extracted_dir / f"{pdf.stem}.json"): pdf
            for pdf in todo
        }
        for future in cf.as_completed(futures):
            pdf = futures[future]
            try:
                future.result()
            except ExtractionSkip as exc:
                stats.skiplisted_new += 1
                skiplist[pdf.stem] = SkipEntry(
                    pdf=str(pdf),
                    reason=str(exc),
                    failed_at=datetime.now(UTC).isoformat(timespec="seconds"),
                )
            else:
                stats.extracted += 1
                # A retried skiplist entry that now extracts is no longer skipped.
                skiplist.pop(pdf.stem, None)
            done += 1
            if done % _PROGRESS_EVERY == 0:
                _save_skiplist(skiplist_path, skiplist)
                rate = done / (time.monotonic() - started)
                eta_min = (len(todo) - done) / rate / 60 if rate else 0
                print(
                    f"  {done}/{len(todo)} this run ({rate:.1f} PDFs/s, ~{eta_min:.0f} min left)",
                    flush=True,
                )

    _save_skiplist(skiplist_path, skiplist)
    elapsed = time.monotonic() - started
    if not stats.total:
        print(f"extract_pdfs: no PDFs found under {pdfs_dir}", flush=True)
        return stats
    ok = stats.extracted + stats.resumed
    failed = stats.skiplisted_new + stats.skiplisted_prior
    print(
        f"extract_pdfs: {stats.total} PDFs -> {ok} extracted "
        f"({stats.resumed} already current), {failed} skiplisted; "
        f"success rate {ok / stats.total:.2%}",
        flush=True,
    )
    print(f"  elapsed {elapsed / 60:.1f} min; skiplist: {skiplist_path}", flush=True)
    return stats


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--workers", type=int, default=settings.extract_workers)
    parser.add_argument(
        "--limit", type=int, default=None, help="evenly strided sample of N PDFs (for dry runs)"
    )
    parser.add_argument(
        "--retry-skipped", action="store_true", help="re-attempt PDFs already on the skiplist"
    )
    args = parser.parse_args(argv)
    run(
        pdfs_dir=settings.pdfs_dir,
        extracted_dir=settings.extracted_dir,
        skiplist_path=settings.skiplist_path,
        workers=args.workers,
        limit=args.limit,
        retry_skipped=args.retry_skipped,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
