"""Download a named list of arXiv ids from the GCS mirror into the corpus.

Every other collector entry point *discovers* what to fetch — newest-first,
evenly sampled, facet-ranked. This one is told. It exists because the landing
page's index frontier (backend `select_frontier.py`) names specific papers,
almost all of them outside any window we pulled: the works our recent cohort
cites are from 2014-2026 and were never candidates for a "recent papers" run.

Metadata comes from the Kaggle snapshot in one streaming pass, exactly as the
discovery paths get it, so a paper fetched here is indistinguishable downstream
from one fetched by `latest` or `diverse`.

Usage:
    fetch_ids.py <ids-file>            # one arxiv id per line, or a frontier.json
    fetch_ids.py <ids-file> --dry-run
"""

import argparse
import concurrent.futures as cf
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import arxiv_ingest as ai


def read_ids(path: Path) -> list[str]:
    """One id per line, or the `paper_ids` of a frontier.json manifest."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return list(json.loads(text)["paper_ids"])
    return [line.strip() for line in text.splitlines() if line.strip()]


def fetch(ids: list[str], *, concurrency: int, dry_run: bool) -> int:
    conn = ai.connect()
    try:
        # already_ingested is the resume check: rerunning after a partial pull
        # costs one SELECT per id, not one download.
        wanted = [aid for aid in ids if not ai.already_ingested(conn, aid)]
        print(
            f"{len(ids)} ids requested, {len(ids) - len(wanted)} already ingested, "
            f"{len(wanted)} to fetch",
            file=sys.stderr,
        )
        if not wanted or dry_run:
            return 0

        want = set(wanted)
        meta: dict[str, dict] = {}
        for rec in ai.seed_records(str(ai.CORPUS_DIR / "archive.zip")):
            if rec["arxiv_id"] in want:
                meta[rec["arxiv_id"]] = rec
                if len(meta) == len(want):
                    break
        missing_meta = sorted(want - meta.keys())
        if missing_meta:
            # Without a version we cannot build the mirror's object path, so
            # these are unfetchable rather than merely un-described.
            print(
                f"  ! {len(missing_meta)} id(s) absent from the Kaggle snapshot, "
                f"skipping (first: {missing_meta[0]})",
                file=sys.stderr,
            )

        def _fetch(aid: str):
            version = meta[aid]["version"]
            url = ai.gcs_pdf_url(aid, version)
            if url is None:
                return aid, version, None
            return aid, version, ai.download_pdf(ai.thread_session(), aid, url, pace=False)

        stored = 0
        todo = [aid for aid in wanted if aid in meta]
        with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(_fetch, aid) for aid in todo]
            for future in cf.as_completed(futures):
                aid, version, path = future.result()
                if path is None:
                    print(f"  ! no PDF on the mirror for {aid} {version}", file=sys.stderr)
                    continue
                rec = {
                    **meta[aid],
                    "version": version,
                    "pdf_path": str(path.relative_to(ai.CORPUS_DIR)),
                    "size_bytes": path.stat().st_size,
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                ai.upsert_paper(conn, rec)
                stored += 1
                print(
                    f"[{stored}/{len(todo)}] {aid} {version}  {rec['title'][:56]!r}",
                    file=sys.stderr,
                )
        print(f"fetch_ids: stored {stored} of {len(todo)}", file=sys.stderr)
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("ids_file", type=Path, help="one arxiv id per line, or a frontier.json")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true", help="report what would be fetched")
    args = parser.parse_args(argv)
    return fetch(read_ids(args.ids_file), concurrency=args.concurrency, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
