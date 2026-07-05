"""corpus/pdfs/** -> corpus/extracted/{arxiv_id}.json + corpus/skiplist.json (D6).

Per-paper output schema — a FROZEN interface, consumed verbatim by the
chunker (#12); changing its shape is spec-amendment territory:

    {"markdown": str,
     "sections": [{"title": str, "page_start": int, "page_end": int}],
     "n_pages": int}

Page numbers are 1-based and inclusive, matching the PDF viewer's #page=N
anchors (D9): a section's content runs from its heading to the next heading,
so adjacent sections share their boundary page. Sections always cover pages
1..n_pages (an untitled preamble/whole-document section fills any gap), so
the chunker can page-anchor every chunk. Failures are recorded, never
silently dropped: skiplist.json maps arxiv_id -> {pdf, reason, failed_at}.
"""

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pymupdf
import pymupdf4llm

from askrag.config import get_settings

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_PROGRESS_EVERY = 100  # completions between progress lines / skiplist flushes


class ExtractionSkip(Exception):
    """Raised for PDFs that cannot be extracted; the message is the skiplist reason."""


def _clean_title(raw: str) -> str:
    # pymupdf4llm renders bold headings as "# **Title**". Titles are section
    # metadata (navigation anchors), not content, so emphasis markers go;
    # the markdown body keeps them.
    return raw.strip().strip("*_").strip()


def extract_one(pdf_path: Path) -> dict:
    """One PDF -> the frozen JSON payload. Raises ExtractionSkip with a reason."""
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ExtractionSkip("encrypted (needs password)")
        n_pages = doc.page_count
        if n_pages == 0:
            raise ExtractionSkip("zero pages")
        # page_chunks=True returns one dict per page; the annotation on
        # to_markdown is too loose for pyright to see that.
        pages = cast(list[dict], pymupdf4llm.to_markdown(doc, page_chunks=True))

    markdown = "".join(page["text"] for page in pages)
    if not markdown.strip():
        raise ExtractionSkip("no extractable text (scanned image PDF?)")

    headings: list[tuple[int, str]] = []
    for page_no, page in enumerate(pages, start=1):
        for match in _HEADING_RE.finditer(page["text"]):
            headings.append((page_no, _clean_title(match.group(1))))

    sections: list[dict] = []
    if not headings or headings[0][0] > 1:
        # Front matter before the first detected heading (or a heading-free
        # document) still needs page anchors for the chunker.
        preamble_end = headings[0][0] if headings else n_pages
        sections.append({"title": "", "page_start": 1, "page_end": preamble_end})
    for i, (page_no, title) in enumerate(headings):
        page_end = headings[i + 1][0] if i + 1 < len(headings) else n_pages
        sections.append({"title": title, "page_start": page_no, "page_end": page_end})

    return {"markdown": markdown, "sections": sections, "n_pages": n_pages}


def _write_json_atomic(path: Path, payload: dict, indent: int | None = None) -> None:
    # A killed run must never leave a truncated JSON that a resume would
    # then trust; rename is atomic on POSIX.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent))
    tmp.replace(path)


def _extract_worker(pdf_path: Path, out_path: Path) -> tuple[str, str]:
    """Pool worker: returns (status, detail); status is 'ok' or 'skip'."""
    try:
        payload = extract_one(pdf_path)
    except ExtractionSkip as exc:
        return "skip", str(exc)
    except Exception as exc:  # corrupt files raise all over pymupdf's C surface
        return "skip", f"{type(exc).__name__}: {exc}"
    _write_json_atomic(out_path, payload)
    return "ok", ""


def _load_skiplist(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_skiplist(path: Path, skiplist: dict[str, dict]) -> None:
    # Sorted + indented: the skiplist is a human-read artifact (issue #11
    # acceptance) and feeds ingest_stats (D12).
    ordered = dict(sorted(skiplist.items()))
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
) -> dict[str, int]:
    """Extract every PDF under pdfs_dir; returns counts for the run summary."""
    extracted_dir.mkdir(parents=True, exist_ok=True)
    skiplist = _load_skiplist(skiplist_path)

    all_pdfs = sorted(pdfs_dir.rglob("*.pdf"))
    if limit is not None and limit < len(all_pdfs):
        # Evenly strided sample: spans the year folders instead of the
        # oldest slice, so sample latency projects onto the full corpus.
        stride = len(all_pdfs) // limit
        all_pdfs = all_pdfs[::stride][:limit]

    todo: list[Path] = []
    resumed = skiplisted_prior = 0
    for pdf in all_pdfs:
        if _is_current(extracted_dir / f"{pdf.stem}.json", pdf):
            resumed += 1
        elif pdf.stem in skiplist and not retry_skipped:
            skiplisted_prior += 1
        else:
            todo.append(pdf)

    stats = {
        "total": len(all_pdfs),
        "resumed": resumed,
        "skiplisted_prior": skiplisted_prior,
        "extracted": 0,
        "skiplisted_new": 0,
    }
    started = time.monotonic()
    done = 0
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_worker, pdf, extracted_dir / f"{pdf.stem}.json"): pdf
            for pdf in todo
        }
        for future in cf.as_completed(futures):
            pdf = futures[future]
            status, detail = future.result()
            if status == "ok":
                stats["extracted"] += 1
                # A retried skiplist entry that now extracts is no longer skipped.
                skiplist.pop(pdf.stem, None)
            else:
                stats["skiplisted_new"] += 1
                skiplist[pdf.stem] = {
                    "pdf": str(pdf),
                    "reason": detail,
                    "failed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
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
    if not stats["total"]:
        print(f"extract_pdfs: no PDFs found under {pdfs_dir}", flush=True)
        return stats
    ok = stats["extracted"] + stats["resumed"]
    failed = stats["skiplisted_new"] + stats["skiplisted_prior"]
    print(
        f"extract_pdfs: {stats['total']} PDFs -> {ok} extracted "
        f"({stats['resumed']} already current), {failed} skiplisted; "
        f"success rate {ok / stats['total']:.2%}",
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
