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

Telemetry (D15): the run emits an askrag.ingest.extract span; each
successful extraction becomes an askrag.ingest.extract.pdf child span
whose timestamps the worker measured itself (spawned workers emit
nothing — see askrag/telemetry.py's process model). Skips surface as
correlated warning logs plus run-span counts, not spans: the exception
that crosses the pool boundary stays message-only.
"""

import argparse
import concurrent.futures as cf
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pymupdf
import pymupdf4llm

from askrag import telemetry
from askrag.config import get_settings

_log = logging.getLogger("askrag.ingest.extract_pdfs")

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
class WorkerTiming:
    """Worker-measured wall clock for one successful extraction; the parent
    turns it into the askrag.ingest.extract.pdf span."""

    start_unix_ns: int
    end_unix_ns: int


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
        # page_chunks=True returns one dict per page; to_markdown's own
        # annotation is too loose for the type checker to see that.
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


def _extract_worker(pdf_path: Path, out_path: Path) -> WorkerTiming:
    """Pool worker. Raises ExtractionSkip (pickle-safe) for every failure mode;
    the pool re-raises it in the parent, which owns the skiplist.

    Returns its own wall-clock (D15 process model): spawned workers have no
    tracer, so they hand timestamps back and the parent emits the span.
    """
    start_unix_ns = time.time_ns()
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
    return WorkerTiming(start_unix_ns=start_unix_ns, end_unix_ns=time.time_ns())


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


def _page_count(pdf_path: Path) -> int:
    # Metadata-only open, no rendering. An unopenable PDF returns 0 so it
    # stays in the sample and fails through the normal skiplist path with a
    # real reason, instead of being silently size-filtered.
    try:
        with pymupdf.open(pdf_path) as doc:
            return doc.page_count
    except Exception:
        return 0


def run(
    pdfs_dir: Path,
    extracted_dir: Path,
    skiplist_path: Path,
    workers: int,
    limit: int | None = None,
    retry_skipped: bool = False,
    sample_max_pages: int = 0,
) -> RunStats:
    """Extract every PDF under pdfs_dir; returns counts for the run summary."""
    extracted_dir.mkdir(parents=True, exist_ok=True)
    skiplist = _load_skiplist(skiplist_path)

    all_pdfs = sorted(pdfs_dir.rglob("*.pdf"))
    if limit is not None and limit < len(all_pdfs):
        # Sampling policy (owner directive 2026-07-05, issue #11): monster
        # papers distort a sample (one 398-page monograph was 10% of all
        # working-sample chunks), so a page cap filters them out BEFORE
        # selection. Full-corpus runs never apply the cap; excluded PDFs are
        # not skiplisted — they are valid papers, just not sample material.
        if sample_max_pages > 0:
            before = len(all_pdfs)
            all_pdfs = [p for p in all_pdfs if _page_count(p) <= sample_max_pages]
            _log.info(
                "sample page cap %d: excluded %d of %d PDFs from selection",
                sample_max_pages,
                before - len(all_pdfs),
                before,
            )
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

    tracer = telemetry.get_tracer("askrag.ingest.extract_pdfs")
    started = time.monotonic()
    done = 0
    with tracer.start_as_current_span("askrag.ingest.extract") as run_span:
        run_span.set_attribute("askrag.pdfs_total", stats.total)
        run_span.set_attribute("askrag.pdfs_todo", len(todo))
        run_span.set_attribute("askrag.workers", workers)
        with cf.ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_extract_worker, pdf, extracted_dir / f"{pdf.stem}.json"): pdf
                for pdf in todo
            }
            for future in cf.as_completed(futures):
                pdf = futures[future]
                try:
                    timing = future.result()
                except ExtractionSkip as exc:
                    stats.skiplisted_new += 1
                    skiplist[pdf.stem] = SkipEntry(
                        pdf=str(pdf),
                        reason=str(exc),
                        failed_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    )
                    # Skips surface as correlated warnings (trace_id from the
                    # run span), never as spans — the reason is on the skiplist.
                    _log.warning(
                        "skiplisted %s: %s",
                        pdf.stem,
                        exc,
                        extra={"askrag_extra": {"askrag.arxiv_id": pdf.stem}},
                    )
                else:
                    stats.extracted += 1
                    # A retried skiplist entry that now extracts is no longer skipped.
                    skiplist.pop(pdf.stem, None)
                    # The worker measured the wall clock; the parent (the only
                    # process with a tracer) emits the child span with those
                    # timestamps.
                    pdf_span = tracer.start_span(
                        "askrag.ingest.extract.pdf",
                        start_time=timing.start_unix_ns,
                        attributes={"askrag.arxiv_id": pdf.stem},
                    )
                    pdf_span.end(end_time=timing.end_unix_ns)
                done += 1
                if done % _PROGRESS_EVERY == 0:
                    _save_skiplist(skiplist_path, skiplist)
                    rate = done / (time.monotonic() - started)
                    eta_min = (len(todo) - done) / rate / 60 if rate else 0
                    print(
                        f"  {done}/{len(todo)} this run "
                        f"({rate:.1f} PDFs/s, ~{eta_min:.0f} min left)",
                        flush=True,
                    )
        run_span.set_attribute("askrag.extracted", stats.extracted)
        run_span.set_attribute("askrag.skiplisted_new", stats.skiplisted_new)

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
    # The entrypoint owns telemetry setup (D15): every CLI calls init() once
    # before any span or log, and flushes on the way out.
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--workers", type=int, default=settings.extract_workers)
    parser.add_argument(
        "--limit", type=int, default=None, help="evenly strided sample of N PDFs (for dry runs)"
    )
    parser.add_argument(
        "--retry-skipped", action="store_true", help="re-attempt PDFs already on the skiplist"
    )
    args = parser.parse_args(argv)
    try:
        run(
            pdfs_dir=settings.pdfs_dir,
            extracted_dir=settings.extracted_dir,
            skiplist_path=settings.skiplist_path,
            workers=args.workers,
            limit=args.limit,
            retry_skipped=args.retry_skipped,
            sample_max_pages=settings.sample_max_pages,
        )
    finally:
        # Flush before exit: the CLI process ends right after the run span, and
        # SimpleSpanProcessor writes synchronously, but OTLP export batches.
        telemetry.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
