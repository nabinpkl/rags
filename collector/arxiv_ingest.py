#!/usr/bin/env python3
"""arXiv full-text corpus collector.

Jobs, one pipeline:

  latest    -- Part 1 (newest-first): pull the most recent papers up to a size
               budget. Seed = category filter, GCS listing = exact per-object
               sizes, so it fills the budget precisely, walking back from today.
  sample    -- Part 1 (temporal spread): N papers per month across all years,
               so the corpus spans time and you can see trends without embeddings.
  diverse   -- Part 1 (diverse spread): per-month blended-facet score spread
               across the impact/topic distribution (authority, niche, novelty,
               revisions, venue rigor). Facets are stored per paper for
               query-time re-ranking. Self-contained (seed + frozen citations).
  backfill  -- Part 1 (oldest-first from a date): seed ids from the Kaggle
               snapshot and download from the GCS mirror until a size budget.
  update    -- RETIRED under D18 (it harvested OAI-PMH from export.arxiv.org).
               Refresh with backfill --seed-file <new-snapshot.zip>
               --source gcs-only --from <last-covered-date> instead.

Downloads PDFs to corpus/pdfs/ and records one metadata row per paper in a
local SQLite index (corpus/arxiv.db), keyed by arxiv_id. The corpus IS the PDF
files; the DB is just an index. No text extraction / chunking -- if you want RAG later, run it
over the collected PDFs then.

Free, no accounts.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import json
import math
import pickle
import random
import re
import sqlite3
import sys
import threading
import time
import zipfile
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

# --- config -----------------------------------------------------------------

# Free, unthrottled full-text mirror (Google/Kaggle-hosted public bucket).
# Layout: .../pdf/{YYMM}/{id}v{N}.pdf  -- individual PDFs, one per version.
GCS_PDF_BASE = "https://storage.googleapis.com/arxiv-dataset/arxiv/arxiv/pdf"
# JSON listing API for the same bucket -- returns per-object sizes, so a
# newest-first pull can hit an exact size budget without downloading first.
GCS_LIST_API = "https://storage.googleapis.com/storage/v1/b/arxiv-dataset/o"
GCS_PDF_PREFIX = "arxiv/arxiv/pdf/"

# arXiv asks bulk/automated users to identify themselves and go easy.
USER_AGENT = "rag-demo-ingester/1.0 (mailto:contact@nabin.org)"
JITTER = 2.0        # extra random 0..JITTER seconds added on top (delay is never below the minimum)
BACKOFF_BASE = 3.0  # exponential retry backoff base: 3, 6, 12, 24, 48 ...
BACKOFF_MAX = 60.0  # cap on a single backoff wait
MAX_RETRIES = 5

# Data artifacts live in the repo-level corpus/ dir (gitignored, spec §4c),
# resolved from this file's location so every command works regardless of cwd.
ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT.parent / "corpus"
DB_PATH = CORPUS_DIR / "arxiv.db"
PDF_DIR = CORPUS_DIR / "pdfs"


_tls = threading.local()


def thread_session() -> requests.Session:
    """A requests.Session per worker thread (Session isn't guaranteed thread-safe)."""
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        _tls.session = s
    return s


# --- storage ----------------------------------------------------------------

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    # corpus/ is gitignored (spec §4c), so a fresh clone doesn't have it, and
    # sqlite3.connect never creates parent directories.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
            arxiv_id    TEXT PRIMARY KEY,
            title       TEXT,
            authors     TEXT,
            abstract    TEXT,
            categories  TEXT,
            datestamp   TEXT,   -- OAI datestamp (when arXiv last touched it)
            published   TEXT,   -- original v1 submission date (YYYY-MM-DD)
            version     TEXT,   -- version of the PDF fetched (e.g. "v4")
            pdf_path    TEXT,   -- path to the downloaded PDF (the actual corpus)
            size_bytes  INTEGER,
            fetched_at  TEXT,
            -- diverse-sample facets (query-time re-ranking; NULL for other modes)
            authority     REAL,     -- head signal: own citations (<=2015) / author authority (2016+)
            niche_idf     REAL,     -- tail signal: max category-tag IDF
            author_novelty REAL,    -- emerging signal: fraction of authors new as of 2020
            revisions     INTEGER,  -- version count of the mirrored PDF
            venue_rigor   INTEGER,  -- 0 none .. 3 top-tier; positive-only (see venue extraction)
            venue         TEXT      -- extracted venue string, if any
        );

        CREATE TABLE IF NOT EXISTS ingest_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    # migrate older DBs: add new columns, drop the now-unused chunks table
    cols = {r[1] for r in conn.execute("PRAGMA table_info(papers)")}
    if "published" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN published TEXT")
    if "version" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN version TEXT")
    if "size_bytes" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN size_bytes INTEGER")
        # backfill sizes for PDFs already on disk from earlier runs
        for aid, rel in conn.execute(
            "SELECT arxiv_id, pdf_path FROM papers WHERE pdf_path IS NOT NULL"
        ).fetchall():
            fp = ROOT / rel
            if fp.exists():
                conn.execute("UPDATE papers SET size_bytes=? WHERE arxiv_id=?",
                             (fp.stat().st_size, aid))
    # diverse-sample facet columns (nullable; guarded so the migration is idempotent)
    for name, decl in (("authority", "REAL"), ("niche_idf", "REAL"),
                       ("author_novelty", "REAL"), ("revisions", "INTEGER"),
                       ("venue_rigor", "INTEGER"), ("venue", "TEXT")):
        if name not in cols:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {decl}")
    conn.execute("DROP TABLE IF EXISTS chunks")
    for legacy in ("n_chars", "n_chunks"):
        if legacy in cols:
            try:
                conn.execute(f"ALTER TABLE papers DROP COLUMN {legacy}")
            except sqlite3.OperationalError:
                pass  # SQLite < 3.35 has no DROP COLUMN; harmless to leave
    conn.commit()
    return conn


def already_ingested(conn: sqlite3.Connection, arxiv_id: str) -> bool:
    """True if this paper's PDF is already recorded (safe to skip)."""
    row = conn.execute("SELECT pdf_path FROM papers WHERE arxiv_id=?", (arxiv_id,)).fetchone()
    return bool(row and row[0])


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM ingest_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO ingest_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


_FACET_DEFAULTS = {"authority": None, "niche_idf": None, "author_novelty": None,
                   "revisions": None, "venue_rigor": None, "venue": None}


def upsert_paper(conn: sqlite3.Connection, rec: dict) -> None:
    """Insert/replace one paper's metadata row. Idempotent by arxiv_id.

    Facet columns default to NULL, so callers that don't compute them (latest,
    sample, backfill, update) pass the same record shape as before.
    """
    row = {**_FACET_DEFAULTS, **rec}
    conn.execute(
        """
        INSERT INTO papers
            (arxiv_id, title, authors, abstract, categories, datestamp, published,
             version, pdf_path, size_bytes, fetched_at,
             authority, niche_idf, author_novelty, revisions, venue_rigor, venue)
        VALUES (:arxiv_id, :title, :authors, :abstract, :categories, :datestamp,
                :published, :version, :pdf_path, :size_bytes, :fetched_at,
                :authority, :niche_idf, :author_novelty, :revisions, :venue_rigor, :venue)
        ON CONFLICT(arxiv_id) DO UPDATE SET
            title=excluded.title, authors=excluded.authors,
            abstract=excluded.abstract, categories=excluded.categories,
            datestamp=excluded.datestamp, published=excluded.published,
            version=excluded.version, pdf_path=excluded.pdf_path,
            size_bytes=excluded.size_bytes, fetched_at=excluded.fetched_at,
            authority=excluded.authority, niche_idf=excluded.niche_idf,
            author_novelty=excluded.author_novelty, revisions=excluded.revisions,
            venue_rigor=excluded.venue_rigor, venue=excluded.venue
        """,
        row,
    )
    conn.commit()


# --- OAI-PMH harvest ---------------------------------------------------------

def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter: 3, 6, 12, 24, 48 (+0..JITTER), capped."""
    return min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX) + random.uniform(0, JITTER)


def _http_get(session: requests.Session, url: str, params: dict | None = None) -> requests.Response:
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, params=params, timeout=60)
            resp.content  # force the body to buffer now, so a mid-stream
            #               truncation (IncompleteRead) raises here and is retried
        except requests.exceptions.RequestException as e:
            # connection reset / IncompleteRead / timeout. Back off and retry
            # rather than drop the paper.
            last_err = e
            wait = _backoff_seconds(attempt)
            print(f"  network error ({e.__class__.__name__}), retry {attempt + 1}/"
                  f"{MAX_RETRIES} in {wait:.0f}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        # Retryable throttle: arXiv sends Retry-After; GCS 429s on bandwidth
        # quota (usually no header) -- fall back to exponential backoff there.
        if resp.status_code in (503, 429):
            hdr = resp.headers.get("Retry-After")
            wait = int(hdr) if hdr and hdr.isdigit() else _backoff_seconds(attempt)
            print(f"  {resp.status_code} throttled, waiting {wait:.0f}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"giving up on {url} after {MAX_RETRIES} retries: {last_err}")


def harvest(session: requests.Session, *, oai_set: str, frm: str, until: str):
    """Retired under D18: the OAI-PMH harvest touched export.arxiv.org.

    Freshness now comes from a new Kaggle snapshot + the GCS mirror
    (`backfill --seed-file ... --source gcs-only`). Kept as a stub so the
    ban is visible at the call site instead of silently reappearing.
    """
    raise NotImplementedError(
        "OAI harvest is retired under D18 (no code path may touch "
        "export.arxiv.org); pull a fresh Kaggle snapshot and backfill from "
        "the GCS mirror instead."
    )


# --- Kaggle seed (offline discovery) ----------------------------------------

def _submitted_date(record: dict) -> str:
    """Original v1 submission date as YYYY-MM-DD, from versions[0].created."""
    versions = record.get("versions") or []
    if not versions:
        return ""
    created = versions[0].get("created", "")
    try:
        return parsedate_to_datetime(created).date().isoformat()
    except (TypeError, ValueError):
        return ""


def seed_records(path: str, *, frm: str | None = None, until: str | None = None,
                 date_field: str = "submitted"):
    """Stream records from the Kaggle arXiv snapshot (JSON-lines).

    Reads straight out of the .zip without extracting the 5+ GB file.
    `date_field` selects what --from/--until filter on: 'submitted' (original
    v1 date) or 'updated' (the snapshot's update_date).
    """
    p = Path(path)
    if p.suffix == ".zip":
        zf = zipfile.ZipFile(p)
        member = next(n for n in zf.namelist() if n.endswith(".json"))
        stream = io.TextIOWrapper(zf.open(member), encoding="utf-8")
    else:
        stream = open(p, encoding="utf-8")
    with stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            upd = r.get("update_date", "") or ""
            submitted = _submitted_date(r)
            key = submitted if date_field == "submitted" else upd
            if frm and key and key < frm:
                continue
            if until and key and key > until:
                continue
            versions = r.get("versions") or []
            latest = versions[-1].get("version", "") if versions else ""
            yield {
                "arxiv_id": r.get("id", ""),
                "title": " ".join((r.get("title") or "").split()),
                "authors": (r.get("authors") or "").strip(),
                "abstract": " ".join((r.get("abstract") or "").split()),
                "categories": r.get("categories", "") or "",
                "datestamp": upd,
                "published": submitted,
                "version": latest,  # e.g. "v4"; needed for the GCS object path
                # extra fields for the diverse sampler (facet inputs)
                "authors_parsed": r.get("authors_parsed") or [],
                "journal_ref": (r.get("journal-ref") or "").strip(),
                "doi": (r.get("doi") or "").strip(),
                "comments": (r.get("comments") or "").strip(),
            }


# --- PDF download + text extraction -----------------------------------------

def pdf_url(arxiv_id: str) -> str:
    """Retired under D18: built an export.arxiv.org PDF URL. Never call it."""
    raise NotImplementedError(
        "the arXiv PDF scraper is retired under D18 (no code path may touch "
        "export.arxiv.org); fetch from the GCS mirror instead."
    )


# new-style ids look like "2401.00003"; old-style like "hep-th/9901001"
_NEW_STYLE_ID = re.compile(r"^\d{4}\.\d{4,5}$")


def gcs_pdf_url(arxiv_id: str, version: str) -> str | None:
    """GCS mirror URL for a specific version, or None if the id isn't mappable.

    Only new-style ids map to the simple .../pdf/{YYMM}/{id}v{N}.pdf layout;
    old-style ids use a different path and are skipped (irrelevant post-2007).
    """
    if not _NEW_STYLE_ID.match(arxiv_id) or not version:
        return None
    yymm = arxiv_id.split(".")[0]
    return f"{GCS_PDF_BASE}/{yymm}/{arxiv_id}{version}.pdf"


def local_pdf_path(arxiv_id: str) -> Path:
    """pdfs/{YYYY}/{MM}/{id}.pdf -- nested year/month folders."""
    safe = arxiv_id.replace("/", "_")
    if _NEW_STYLE_ID.match(arxiv_id):
        yymm = arxiv_id.split(".")[0]        # e.g. "2606"
        return PDF_DIR / f"20{yymm[:2]}" / yymm[2:] / f"{safe}.pdf"  # 2026/06/
    return PDF_DIR / "misc" / f"{safe}.pdf"


def download_pdf(session: requests.Session, arxiv_id: str, url: str) -> Path | None:
    dest = local_pdf_path(arxiv_id)
    if dest.exists() and dest.stat().st_size > 0:
        return dest  # already have it
    try:
        resp = _http_get(session, url)
    except Exception as e:  # noqa: BLE001 - demo: log and move on
        print(f"  ! download failed {arxiv_id}: {e}", file=sys.stderr)
        return None
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" not in ctype.lower():
        # the mirror sometimes serves an XML error document for a missing key
        print(f"  ! {arxiv_id}: not a pdf ({ctype})", file=sys.stderr)
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def fetch_pdf(session: requests.Session, rec: dict, source: str) -> Path | None:
    """Fetch a paper's PDF from the GCS mirror (the only source since D18)."""
    if source == "arxiv":
        raise NotImplementedError(
            "source=arxiv is retired under D18 (no code path may touch "
            "export.arxiv.org); use --source gcs-only with a Kaggle seed."
        )
    arxiv_id = rec["arxiv_id"]
    url = gcs_pdf_url(arxiv_id, rec.get("version", ""))
    if url is None:
        print(f"  ! {arxiv_id}: not on GCS mirror (old-style id / no version); skipping",
              file=sys.stderr)
        return None
    path = download_pdf(session, arxiv_id, url)
    if path is not None:
        return path
    # Mirror lag is the common cause (it syncs on Sundays); the paper
    # will be there next sync. The GCS-miss fallback to the arXiv scraper
    # is retired under D18 — a miss is skipped, never re-fetched elsewhere.
    print(f"  gcs miss for {arxiv_id}; gcs-only, skipping", file=sys.stderr)
    return None


# --- pipeline ----------------------------------------------------------------

def process_record(conn, session, rec: dict, source: str) -> int:
    """Download one PDF and record its metadata row. Returns PDF bytes stored."""
    arxiv_id = rec["arxiv_id"]
    if not arxiv_id:
        return 0
    pdf_path = fetch_pdf(session, rec, source)
    if pdf_path is None:
        return 0
    size = pdf_path.stat().st_size
    rec = {
        **rec,
        "version": rec.get("version", ""),  # ensure present for the insert
        "pdf_path": str(pdf_path.relative_to(CORPUS_DIR)),
        "size_bytes": size,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        upsert_paper(conn, rec)
    except Exception as e:  # noqa: BLE001 - one bad paper must not kill the run
        print(f"  ! store failed {arxiv_id}: {e}", file=sys.stderr)
        return 0
    return size


def run(*, oai_set: str, frm: str, until: str, max_gb: float | None, limit: int | None,
        category_prefix: str | None, seed_file: str | None = None,
        date_field: str = "submitted", skip_existing: bool = False,
        source: str = "gcs-only", concurrency: int = 1) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    budget = int(max_gb * 1024**3) if max_gb else None
    stored_bytes = 0
    n = 0
    skipped = 0
    parallel = concurrency > 1
    batch: list[dict] = []

    if seed_file:
        print(f"seeding ids from {seed_file} ({date_field} date {frm}..{until}) "
              f"source={source} concurrency={concurrency if parallel else 1} "
              f"(budget={max_gb or '∞'} GB, limit={limit or '∞'})", file=sys.stderr)
        records = seed_records(seed_file, frm=frm, until=until, date_field=date_field)
    else:
        raise NotImplementedError(
            "seedless discovery used the OAI-PMH harvest, retired under D18 "
            "(no code path may touch export.arxiv.org); pass --seed-file with "
            "a Kaggle snapshot instead."
        )

    def flush() -> bool:
        """Fetch the buffered batch concurrently, upsert here. True if done."""
        nonlocal stored_bytes, n
        if not batch:
            return False

        def worker(r):
            return r, fetch_pdf(thread_session(), r, source)

        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = [ex.submit(worker, r) for r in batch]
            for fut in cf.as_completed(futs):
                r, path = fut.result()
                if path is None:
                    continue
                size = path.stat().st_size
                rec2 = {**r, "version": r.get("version", ""),
                        "pdf_path": str(path.relative_to(CORPUS_DIR)), "size_bytes": size,
                        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                try:
                    upsert_paper(conn, rec2)
                except Exception as e:  # noqa: BLE001
                    print(f"  ! store failed {r['arxiv_id']}: {e}", file=sys.stderr)
                    continue
                stored_bytes += size
                n += 1
                print(f"[{n}] {r['arxiv_id']}  {r['title'][:66]!r}  "
                      f"({stored_bytes / 1024**3:.2f} GB)", file=sys.stderr)
        batch.clear()
        return bool(budget and stored_bytes >= budget) or bool(limit and n >= limit)

    stopped = False
    for rec in records:
        if category_prefix and not rec["categories"].startswith(category_prefix):
            # OAI sets are coarse (e.g. "cs"); narrow to cs.CL etc. here.
            continue
        if skip_existing and already_ingested(conn, rec["arxiv_id"]):
            # backfill resume: already have it, don't re-download.
            # still count its on-disk size so the budget reflects total stored.
            p = local_pdf_path(rec["arxiv_id"])
            if p.exists():
                stored_bytes += p.stat().st_size
            skipped += 1
            if budget and stored_bytes >= budget:
                print(f"reached size budget ({stored_bytes / 1024**3:.2f} GB), stopping.",
                      file=sys.stderr)
                stopped = True
                break
            continue

        if parallel:
            batch.append(rec)
            if len(batch) >= concurrency * 4:
                if flush():
                    print(f"reached budget/limit, stopping "
                          f"({stored_bytes / 1024**3:.2f} GB).", file=sys.stderr)
                    stopped = True
                    break
            continue

        size = process_record(conn, session, rec, source)
        if size:
            stored_bytes += size
            n += 1
            print(f"[{n}] {rec['arxiv_id']}  {rec['title'][:70]!r}  "
                  f"({stored_bytes / 1024**3:.2f} GB)", file=sys.stderr)
        if budget and stored_bytes >= budget:
            print(f"reached size budget ({stored_bytes / 1024**3:.2f} GB), stopping.",
                  file=sys.stderr)
            stopped = True
            break
        if limit and n >= limit:
            print(f"reached limit ({limit} papers), stopping.", file=sys.stderr)
            stopped = True
            break

    if parallel and not stopped:
        flush()  # drain the remaining buffered records

    # advance the incremental watermark to this run's `until`
    set_state(conn, "last_until", until)
    conn.close()
    tail = f" ({skipped} already present, skipped)" if skipped else ""
    print(f"done. {n} new papers, {stored_bytes / 1024**3:.2f} GB in {PDF_DIR}{tail}",
          file=sys.stderr)


# --- latest (newest-first, exact budget via GCS listing) --------------------

def _gcs_list(session: requests.Session, params: dict) -> dict:
    return _http_get(session, GCS_LIST_API, params).json()


_MONTH_RE = re.compile(r"^\d{4}$")
_OBJ_RE = re.compile(r"(\d{4}\.\d{4,5})v(\d+)\.pdf$")


def gcs_months(session: requests.Session) -> list[str]:
    """All YYMM month folders present under pdf/ (via bucket listing)."""
    months, token = [], None
    while True:
        params = {"prefix": GCS_PDF_PREFIX, "delimiter": "/", "maxResults": 1000}
        if token:
            params["pageToken"] = token
        d = _gcs_list(session, params)
        for pfx in d.get("prefixes", []):
            m = pfx.rstrip("/").rsplit("/", 1)[-1]
            if _MONTH_RE.match(m):
                months.append(m)
        token = d.get("nextPageToken")
        if not token:
            return months


def gcs_month_objects(session: requests.Session, yymm: str):
    """Yield (arxiv_id, version_int, size_bytes) for every PDF in a month."""
    prefix, token = f"{GCS_PDF_PREFIX}{yymm}/", None
    while True:
        params = {"prefix": prefix, "maxResults": 1000}
        if token:
            params["pageToken"] = token
        d = _gcs_list(session, params)
        for it in d.get("items", []):
            m = _OBJ_RE.search(it["name"])
            if m:
                yield m.group(1), int(m.group(2)), int(it.get("size", 0))
        token = d.get("nextPageToken")
        if not token:
            return


def run_latest(*, seed_file: str, category_prefix: str | None,
               max_gb: float, limit: int | None, concurrency: int = 8) -> None:
    """Newest-first pull of up to max_gb, exact via GCS per-object sizes.

    Seed = category filter (which ids are cs.*); GCS listing = the sizes. We
    select the newest matching papers whose sizes sum to <= budget, then
    download exactly those. Only the selected PDFs are ever downloaded.
    """
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    budget = int(max_gb * 1024**3)

    # 1) which ids match the category (local seed scan, downloads nothing)
    print(f"scanning seed for {category_prefix or 'all'} ids...", file=sys.stderr)
    wanted_cat = set()
    for rec in seed_records(seed_file):
        if not category_prefix or rec["categories"].startswith(category_prefix):
            wanted_cat.add(rec["arxiv_id"])
    print(f"  {len(wanted_cat):,} candidate ids in seed", file=sys.stderr)

    # 2) walk GCS months newest-first, take newest matches until the budget fills
    selected, total = [], 0  # selected: list of (id, version_int, size)
    for mo in sorted(gcs_months(session), reverse=True):
        latest: dict[str, tuple[int, int]] = {}  # id -> (version_int, size)
        for aid, vn, size in gcs_month_objects(session, mo):
            if aid in wanted_cat and (aid not in latest or vn > latest[aid][0]):
                latest[aid] = (vn, size)
        stop = False
        for aid in sorted(latest, reverse=True):  # newest id first within month
            vn, size = latest[aid]
            if total + size > budget:
                stop = True
                break
            selected.append((aid, vn, size))
            total += size
            if limit and len(selected) >= limit:
                stop = True
                break
        print(f"  {mo}: {total / 1024**3:.2f} GB / {len(selected)} papers", file=sys.stderr)
        if stop:
            break
    if not selected:
        print("nothing selected (no matching papers on the mirror).", file=sys.stderr)
        conn.close()
        return
    newest, oldest = selected[0][0], selected[-1][0]
    print(f"selected {len(selected)} papers, {total / 1024**3:.2f} GB "
          f"(newest {newest} .. oldest {oldest}). fetching metadata...", file=sys.stderr)

    n, got = _download_selected(conn, seed_file, selected, concurrency)
    # after grabbing the latest, updates should track new arrivals from today
    set_state(conn, "last_until", today())
    conn.close()
    print(f"done. {n} new papers, {got / 1024**3:.2f} GB in {PDF_DIR}", file=sys.stderr)


def _download_selected(conn, seed_file: str, selected: list, concurrency: int,
                       extra: dict[str, dict] | None = None) -> tuple[int, int]:
    """Fetch metadata (seed scan) then download `selected` [(id, ver, size)] from
    GCS concurrently, upserting on this thread. Returns (new_count, total_bytes).

    `extra` maps arxiv_id -> extra column values (e.g. diverse-sample facets)
    merged into each stored row."""
    extra = extra or {}
    want_ids = {aid for aid, _, _ in selected}
    meta: dict[str, dict] = {}
    for rec in seed_records(seed_file):
        if rec["arxiv_id"] in want_ids:
            meta[rec["arxiv_id"]] = rec
            if len(meta) == len(want_ids):
                break

    n, got, work = 0, 0, []
    for aid, vn, size in selected:
        if already_ingested(conn, aid):
            got += size
            continue
        work.append((aid, f"v{vn}"))
    print(f"downloading {len(work)} PDFs (concurrency={concurrency})...", file=sys.stderr)

    def _fetch(item):
        aid, ver = item
        return aid, ver, download_pdf(thread_session(), aid, gcs_pdf_url(aid, ver))

    with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = [ex.submit(_fetch, it) for it in work]
        for fut in cf.as_completed(futs):
            aid, ver, path = fut.result()
            if path is None:
                continue
            base = meta.get(aid, {"arxiv_id": aid, "title": "", "authors": "",
                                  "abstract": "", "categories": "", "datestamp": "",
                                  "published": ""})
            rec = {**base, "arxiv_id": aid, "version": ver,
                   "pdf_path": str(path.relative_to(CORPUS_DIR)),
                   "size_bytes": path.stat().st_size,
                   "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   **(extra.get(aid) or {})}
            try:
                upsert_paper(conn, rec)
            except Exception as e:  # noqa: BLE001
                print(f"  ! store failed {aid}: {e}", file=sys.stderr)
                continue
            n += 1
            got += rec["size_bytes"]
            print(f"[{n}/{len(work)}] {aid} {ver}  {base.get('title', '')[:56]!r}  "
                  f"({got / 1024**3:.2f} GB)", file=sys.stderr)
    return n, got


def _even_sample(items: list, k: int) -> list:
    """k items spread evenly across a sorted list (deterministic, representative)."""
    if k <= 0 or not items:
        return []
    if len(items) <= k:
        return list(items)
    idxs = sorted({round(i * (len(items) - 1) / (k - 1)) for i in range(k)}) if k > 1 \
        else [len(items) // 2]
    return [items[i] for i in idxs]


def run_sample(*, seed_file: str, category_prefix: str | None, per_month: int,
               concurrency: int, from_year: int | None, to_year: int | None,
               max_gb: float | None) -> None:
    """Temporal sample: `per_month` papers spread across each month, all years.

    Gives a corpus that spans time so you can see how the field's titles/topics
    shift, no embeddings needed. Seed = category filter; GCS listing = sizes.
    """
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    budget = int(max_gb * 1024**3) if max_gb else None

    print(f"scanning seed for {category_prefix or 'all'} ids...", file=sys.stderr)
    wanted_cat = set()
    for rec in seed_records(seed_file):
        if not category_prefix or rec["categories"].startswith(category_prefix):
            wanted_cat.add(rec["arxiv_id"])
    print(f"  {len(wanted_cat):,} candidate ids in seed", file=sys.stderr)

    selected, total, stop = [], 0, False
    for mo in sorted(gcs_months(session)):  # chronological (oldest first)
        yr = 2000 + int(mo[:2])
        if (from_year and yr < from_year) or (to_year and yr > to_year):
            continue
        cands: dict[str, tuple[int, int]] = {}
        for aid, vn, size in gcs_month_objects(session, mo):
            if aid in wanted_cat and (aid not in cands or vn > cands[aid][0]):
                cands[aid] = (vn, size)
        if not cands:
            continue
        picks = _even_sample(sorted(cands), per_month)
        took = 0
        for aid in picks:
            vn, size = cands[aid]
            if budget and total + size > budget:
                stop = True
                break
            selected.append((aid, vn, size))
            total += size
            took += 1
        print(f"  {mo} (20{mo[:2]}-{mo[2:]}): {took}/{len(cands)} sampled, "
              f"cum {total / 1024**3:.2f} GB", file=sys.stderr)
        if stop:
            break
    if not selected:
        print("nothing selected.", file=sys.stderr)
        conn.close()
        return
    print(f"selected {len(selected)} papers across {len({s[0][:4] for s in selected})} "
          f"months, {total / 1024**3:.2f} GB. fetching metadata...", file=sys.stderr)

    n, got = _download_selected(conn, seed_file, selected, concurrency)
    conn.close()  # sample is not a forward corpus; leave the update watermark alone
    print(f"done. {n} new sampled papers, {got / 1024**3:.2f} GB in {PDF_DIR}", file=sys.stderr)


# --- diverse sample: a budget-bounded, diverse cs corpus --------------------
# See docs/superpowers/specs/2026-07-03-diverse-cs-sample-design.md.
# Selection is one blended, rank-normalised score spread (not top-K) across five
# self-contained facets; the facets are also stored per paper for query-time
# re-ranking. Signals: authority (head), niche_idf (tail), author_novelty
# (emerging), revisions (maturity), venue_rigor (rigor).

DATA_DIR = CORPUS_DIR / "data"
CITATIONS_URL = ("https://storage.googleapis.com/arxiv-dataset/"
                 "metadata-v5/internal-citations.json")


def _ensure_local(path_or_url: str, cache: Path) -> Path:
    """Return a local path for `path_or_url`. Local paths pass through; URLs are
    streamed to `cache` once (skipped if already present)."""
    if not path_or_url.startswith(("http://", "https://")):
        return Path(path_or_url)
    if cache.exists() and cache.stat().st_size > 0:
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {path_or_url} -> {cache} ...", file=sys.stderr)
    with requests.get(path_or_url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp = cache.with_suffix(cache.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.rename(cache)
    return cache

# --- venue rigor: extraction + tiering ---

# DOI registrant prefix -> (publisher label, floor tier). A few publishers imply
# a top venue (ACL Anthology, Nature); most only imply "peer-reviewed" (tier 1).
_DOI_PREFIX = {
    "10.18653": ("ACL", 3),   # ACL Anthology (ACL/EMNLP/NAACL/TACL/CL)
    "10.1038": ("Nature", 3),
    "10.1126": ("Science", 3),
    "10.1073": ("PNAS", 3),
    "10.1103": ("APS", 2),    # Physical Review family
    "10.1109": ("IEEE", 1),
    "10.1145": ("ACM", 1),
    "10.1007": ("Springer", 1),
    "10.1016": ("Elsevier", 1),
    "10.1017": ("CUP", 1),
    "10.1093": ("OUP", 1),
    "10.5555": ("proceedings", 1),
}

# Curated top-tier (A*/A) cs venues + top journals -> tier 3. A cached CORE CSV,
# when supplied, augments this with B/C tiers (see load_core_tiers).
_TOP_VENUES = {
    "neurips", "nips", "icml", "iclr", "aaai", "ijcai", "uai", "aistats",
    "colt", "kdd", "cvpr", "iccv", "eccv", "acl", "emnlp", "naacl", "coling",
    "interspeech", "siggraph",
    "stoc", "focs", "soda", "pldi", "popl", "oopsla", "osdi", "sosp", "nsdi",
    "sigcomm", "sigmod", "vldb", "pods", "icde", "ccs", "ndss", "usenix",
    "www", "chi", "micro", "isca", "hpca", "asplos", "mobicom", "rss", "corl",
    "jmlr", "tacl", "tpami", "pami", "jacm", "cacm",
}

_VENUE_TOKEN_RE = re.compile(
    r"\b(" + "|".join(sorted(_TOP_VENUES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_ACCEPT_CUE_RE = re.compile(
    r"\b(accepted|to appear|camera.?ready|proceedings of|in proceedings|"
    r"published in|appears? in|forthcoming)\b",
    re.IGNORECASE,
)


def load_core_tiers(path: str | None) -> dict[str, int]:
    """Parse a CORE conference-rankings CSV into {acronym_lower: tier}.

    CORE rows look like: id,Title,Acronym,Source,Rank,... -> A*/A map to 3,
    B/C to 2. A missing/unreadable file yields {} (we fall back to _TOP_VENUES).
    """
    tiers: dict[str, int] = {}
    if not path or not Path(path).exists():
        return tiers
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            acr = (row[2] or "").strip().lower()
            rank = (row[4] or "").strip().upper()
            if not acr:
                continue
            if rank in ("A*", "A"):
                tiers[acr] = 3
            elif rank in ("B", "C"):
                tiers.setdefault(acr, 2)
    return tiers


def _venue_tier(token: str, core: dict[str, int]) -> int:
    key = token.strip().lower()
    if key in _TOP_VENUES:
        return 3
    return core.get(key, 0)


def extract_venue(journal_ref: str, doi: str, comments: str,
                  core: dict[str, int] | None = None) -> tuple[str | None, int]:
    """Best-effort (venue, rigor 0-3) from metadata.

    Positive-only: rigor 0 means 'no venue detected', never 'unpublished'
    (cs authors rarely backfill arXiv -- see spec 'Venue rigor'). Precision
    order: comments-with-acceptance-cue > journal-ref > doi prefix.
    """
    core = core or {}
    best_venue, best_tier = None, 0

    def consider(venue, tier):
        nonlocal best_venue, best_tier
        if tier > best_tier:
            best_venue, best_tier = venue, tier
        elif best_venue is None and venue:
            best_venue = venue

    # 1) comments: acceptance cue + a known top-venue token is the strongest cs
    #    signal; a bare token (no cue) is a weaker "mentions a venue" hint.
    if comments:
        m = _VENUE_TOKEN_RE.search(comments)
        if m and _ACCEPT_CUE_RE.search(comments):
            consider(m.group(1).upper(), _venue_tier(m.group(1), core) or 3)
        elif m:
            consider(m.group(1).upper(), 2)

    # 2) journal-ref: a top venue named in it -> tier 3; otherwise a real
    #    journal string is at least "published-generic".
    if journal_ref:
        m = _VENUE_TOKEN_RE.search(journal_ref)
        if m:
            consider(m.group(1).upper(), _venue_tier(m.group(1), core) or 3)
        else:
            consider(journal_ref.split(",")[0].strip()[:60] or None, 1)

    # 3) doi prefix -> publisher / floor tier
    if doi.startswith("10."):
        pfx = doi.split("/")[0]
        label, tier = _DOI_PREFIX.get(pfx, ("published", 1))
        consider(label, tier)

    return best_venue, best_tier


# --- signal tables ---

_CIT_ENTRY_RE = re.compile(r'"[^"]+":\s*\[([^\]]*)\]')
_CIT_ID_RE = re.compile(r'"([^"]+)"')


def build_indegree(citations_path: str) -> dict[str, int]:
    """Citation in-degree per paper from internal-citations.json.

    The file is one big {citing_id: [cited_id, ...]} object. We regex each
    value-list and count cited-id occurrences, so keys (citing ids) are never
    miscounted. Frozen ~2020 -> only pre-2020 papers get non-zero scores.
    """
    data = Path(citations_path).read_text(encoding="utf-8")
    indeg: dict[str, int] = {}
    for m in _CIT_ENTRY_RE.finditer(data):
        for cid in _CIT_ID_RE.findall(m.group(1)):
            indeg[cid] = indeg.get(cid, 0) + 1
    return indeg


def _author_key(last: str, first: str) -> str:
    """last-name + first-initial, lowercased. Deliberately coarse (collisions vs
    fragmentation trade-off); `max` aggregation downstream limits the damage."""
    return f"{last.strip().lower()}|{first.strip()[:1].lower()}"


def build_author_tables(seed_file: str, indeg: dict[str, int]):
    """(author_authority, pre2020_authors) from pre-2020 (<=2019) papers.

    author_authority[key] = sum of in-degrees of that author's <=2019 papers;
    pre2020_authors = every author key seen in a <=2019 paper (for novelty).
    """
    author_auth: dict[str, int] = {}
    pre_authors: set[str] = set()
    for rec in seed_records(seed_file):
        yr = rec["published"][:4]
        if not yr or yr > "2019":
            continue
        cites = indeg.get(rec["arxiv_id"], 0)
        for a in rec["authors_parsed"]:
            if not a:
                continue
            k = _author_key(a[0], a[1] if len(a) > 1 else "")
            pre_authors.add(k)
            if cites:
                author_auth[k] = author_auth.get(k, 0) + cites
    return author_auth, pre_authors


class Facets(tuple):
    """(authority, niche_idf, author_novelty, venue_rigor, venue, has_abstract)."""
    __slots__ = ()
    authority = property(lambda s: s[0])
    niche_idf = property(lambda s: s[1])
    author_novelty = property(lambda s: s[2])
    venue_rigor = property(lambda s: s[3])
    venue = property(lambda s: s[4])
    has_abstract = property(lambda s: s[5])


def build_facets(seed_file: str, category_prefix: str | None,
                 indeg: dict[str, int], author_auth: dict[str, int],
                 pre_authors: set[str], core: dict[str, int]) -> dict[str, Facets]:
    """Per-cs-paper facet record. Two logical passes fused into one seed scan:
    accumulate category document-frequency while stashing each paper's inputs,
    then fold in niche_idf once N and df are complete."""
    df: dict[str, int] = {}
    n_docs = 0
    stash: dict[str, tuple] = {}  # id -> (authority, novelty, rigor, venue, has_abs, tags)
    prefix = category_prefix or "cs"
    for rec in seed_records(seed_file):
        cats = rec["categories"].split()
        if not any(c.startswith(prefix) for c in cats):
            continue
        n_docs += 1
        for c in cats:
            df[c] = df.get(c, 0) + 1
        yr = rec["published"][:4]
        if yr and yr <= "2015":
            authority = float(indeg.get(rec["arxiv_id"], 0))
        else:
            authority = float(max((author_auth.get(_author_key(a[0], a[1] if len(a) > 1 else ""), 0)
                                   for a in rec["authors_parsed"] if a), default=0))
        authors = [a for a in rec["authors_parsed"] if a]
        if authors:
            new = sum(1 for a in authors
                      if _author_key(a[0], a[1] if len(a) > 1 else "") not in pre_authors)
            novelty = new / len(authors)
        else:
            novelty = 0.0
        venue, rigor = extract_venue(rec["journal_ref"], rec["doi"], rec["comments"], core)
        stash[rec["arxiv_id"]] = (authority, novelty, rigor, venue,
                                  bool(rec["abstract"]), tuple(cats))
    facets: dict[str, Facets] = {}
    for aid, (authority, novelty, rigor, venue, has_abs, tags) in stash.items():
        min_df = min((df[t] for t in tags), default=n_docs)
        niche = math.log(n_docs / min_df) if min_df else 0.0
        facets[aid] = Facets((authority, niche, novelty, rigor, venue, has_abs))
    return facets


def _diverse_tables(seed_file: str, category_prefix: str | None,
                    citations_file: str, core_file: str | None):
    """Load (or build+cache) the facet table. Cache key = input file mtimes +
    category prefix, so an unchanged corpus reuses the ~2-3 min build."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sig = "|".join(str(x) for x in (
        int(Path(seed_file).stat().st_mtime), int(Path(citations_file).stat().st_mtime),
        int(Path(core_file).stat().st_mtime) if core_file and Path(core_file).exists() else 0,
        category_prefix or "cs"))
    import hashlib
    cache = DATA_DIR / f"facets_{hashlib.md5(sig.encode()).hexdigest()[:12]}.pkl"
    if cache.exists():
        # Trusted local cache: this process is the only writer (below), under the
        # repo's own corpus/data/ dir. Not loaded from any external/untrusted source.
        print(f"loading cached facet table {cache.name}...", file=sys.stderr)
        with open(cache, "rb") as f:
            return pickle.load(f)
    print("building citation in-degree...", file=sys.stderr)
    indeg = build_indegree(citations_file)
    print(f"  {len(indeg):,} cited ids. building author authority...", file=sys.stderr)
    author_auth, pre_authors = build_author_tables(seed_file, indeg)
    print(f"  {len(author_auth):,} authors scored. building facets...", file=sys.stderr)
    core = load_core_tiers(core_file)
    facets = build_facets(seed_file, category_prefix, indeg, author_auth, pre_authors, core)
    print(f"  {len(facets):,} {category_prefix or 'cs'} papers scored.", file=sys.stderr)
    with open(cache, "wb") as f:
        pickle.dump(facets, f)
    return facets


# --- scoring ---

def rank_normalize(values: list[float]) -> list[float]:
    """Map values to [0,1] by rank (ties share the mean rank). Robust to the
    heavy-tailed raw facet distributions. A constant list maps to all-0.5."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


DEFAULT_WEIGHTS = {"authority": 0.30, "niche": 0.20, "novelty": 0.15,
                   "revisions": 0.10, "venue": 0.25}


def parse_weights(spec: str | None) -> dict[str, float]:
    w = dict(DEFAULT_WEIGHTS)
    if spec:
        for part in spec.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip() in w:
                    w[k.strip()] = float(v)
    return w


def composite_scores(rows: list[dict], weights: dict[str, float]) -> list[float]:
    """Blended score per candidate: weighted sum of the five rank-normalised
    facets. `rows` are dicts with raw facet values."""
    dims = {
        "authority": rank_normalize([r["authority"] for r in rows]),
        "niche": rank_normalize([r["niche_idf"] for r in rows]),
        "novelty": rank_normalize([r["author_novelty"] for r in rows]),
        "revisions": rank_normalize([float(r["revisions"]) for r in rows]),
        "venue": rank_normalize([float(r["venue_rigor"]) for r in rows]),
    }
    return [sum(weights[d] * dims[d][i] for d in weights) for i in range(len(rows))]


def run_diverse(*, seed_file: str, category_prefix: str | None, per_month: int,
                max_gb: float | None, concurrency: int, from_year: int | None,
                to_year: int | None, citations_file: str, core_file: str | None,
                weights: dict[str, float], min_kb: int = 50) -> None:
    """Diverse, budget-bounded cs sample: per month, score candidates by the
    blended facet score and take `per_month` spread across it (not top-K), so
    the sample spans canonical -> mid -> tail. Facets are stored per paper."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    facets = _diverse_tables(seed_file, category_prefix, citations_file, core_file)
    budget = int(max_gb * 1024**3) if max_gb else None

    selected, extra, total, stop = [], {}, 0, False
    rigor_hist = {0: 0, 1: 0, 2: 0, 3: 0}
    for mo in sorted(gcs_months(session)):  # chronological (oldest first)
        yr = 2000 + int(mo[:2])
        if (from_year and yr < from_year) or (to_year and yr > to_year):
            continue
        # newest version + its size per id present in this month
        obj: dict[str, tuple[int, int]] = {}
        for aid, vn, size in gcs_month_objects(session, mo):
            if aid in facets and (aid not in obj or vn > obj[aid][0]):
                obj[aid] = (vn, size)
        # Idempotent top-up: papers already in the store for this month count
        # toward the per_month floor, so re-runs converge instead of piling on.
        have = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE arxiv_id LIKE ? AND pdf_path IS NOT NULL",
            (f"{mo}.%",)).fetchone()[0]
        need = per_month - have
        if need <= 0:
            continue
        rows = []
        for aid, (vn, size) in obj.items():
            f = facets[aid]
            if already_ingested(conn, aid) or not f.has_abstract or size < min_kb * 1024:
                continue
            rows.append({"aid": aid, "vn": vn, "size": size, "authority": f.authority,
                         "niche_idf": f.niche_idf, "author_novelty": f.author_novelty,
                         "revisions": vn, "venue_rigor": f.venue_rigor, "venue": f.venue})
        if not rows:
            continue
        scores = composite_scores(rows, weights)
        ranked = [rows[i] for i in sorted(range(len(rows)), key=lambda i: scores[i])]
        picks = _even_sample(ranked, need)  # spread across the score, up to the floor
        took = 0
        for r in picks:
            if budget and total + r["size"] > budget:
                stop = True
                break
            selected.append((r["aid"], r["vn"], r["size"]))
            extra[r["aid"]] = {"authority": r["authority"], "niche_idf": r["niche_idf"],
                               "author_novelty": r["author_novelty"], "revisions": r["revisions"],
                               "venue_rigor": r["venue_rigor"], "venue": r["venue"]}
            rigor_hist[r["venue_rigor"]] = rigor_hist.get(r["venue_rigor"], 0) + 1
            total += r["size"]
            took += 1
        print(f"  {mo} (20{mo[:2]}-{mo[2:]}): {took}/{len(rows)} picked, "
              f"cum {total / 1024**3:.2f} GB", file=sys.stderr)
        if stop:
            break
    if not selected:
        print("nothing selected.", file=sys.stderr)
        conn.close()
        return
    n_months = len({s[0][:4] for s in selected})
    print(f"selected {len(selected)} papers across {n_months} months, "
          f"{total / 1024**3:.2f} GB. venue_rigor histogram "
          f"(0/1/2/3): {rigor_hist[0]}/{rigor_hist[1]}/{rigor_hist[2]}/{rigor_hist[3]}",
          file=sys.stderr)

    n, got = _download_selected(conn, seed_file, selected, concurrency, extra=extra)
    conn.close()  # diverse shapes the corpus; leave the update watermark alone
    print(f"done. {n} new papers, {got / 1024**3:.2f} GB in {PDF_DIR}", file=sys.stderr)


def run_reorganize() -> None:
    """Move every PDF under pdfs/ to its pdfs/{YYYY}/{MM}/ home and fix DB paths.

    Layout-agnostic and idempotent: works from a flat pdfs/*.pdf or an older
    pdfs/{YYMM}/ layout, and does nothing if already organized.
    """
    conn = connect()
    moved = 0
    for f in list(PDF_DIR.rglob("*.pdf")):
        arxiv_id = f.stem.replace("_", "/")  # reverse the safe() transform
        dest = local_pdf_path(arxiv_id)
        if dest.resolve() == f.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.rename(dest)
        moved += 1
    # prune directories left empty by the moves (deepest first)
    for d in sorted((p for p in PDF_DIR.rglob("*") if p.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    fixed = 0
    for aid, rel in conn.execute(
        "SELECT arxiv_id, pdf_path FROM papers WHERE pdf_path IS NOT NULL"
    ).fetchall():
        want = str(local_pdf_path(aid).relative_to(CORPUS_DIR))
        if rel != want:
            conn.execute("UPDATE papers SET pdf_path=? WHERE arxiv_id=?", (want, aid))
            fixed += 1
    conn.commit()
    conn.close()
    print(f"reorganized {moved} PDFs into {PDF_DIR}/<YYYY>/<MM>/  ({fixed} DB paths updated)",
          file=sys.stderr)


# --- cli ---------------------------------------------------------------------

def today() -> str:
    return date.today().isoformat()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backfill", help="Part 1: bulk historical pull up to a size budget")
    b.add_argument("--set", default="cs", help="OAI set / archive (e.g. cs, math, physics:hep-th)")
    b.add_argument("--category-prefix", default=None,
                   help="narrow within the set, e.g. cs.CL (matches primary category prefix)")
    b.add_argument("--from", dest="frm", default="2024-01-01", help="start date YYYY-MM-DD")
    b.add_argument("--until", default=today(), help="end date YYYY-MM-DD")
    b.add_argument("--max-gb", type=float, default=4.0, help="stop once this many GB of PDFs stored")
    b.add_argument("--limit", type=int, default=None, help="stop after N papers (overrides size)")
    b.add_argument("--seed-file", default=None,
                   help="Kaggle arXiv snapshot (.zip or .json) to discover ids offline, "
                        "instead of crawling OAI-PMH.")
    b.add_argument("--source", choices=["gcs", "gcs-only"], default="gcs",
                    help="where to download PDFs: gcs = free unthrottled Google mirror "
                         "(default, needs --seed-file for versions; a miss is skipped, "
                         "never re-fetched — the arXiv fallback is retired under D18); "
                         "gcs-only = mirror only, explicit about it (same behavior)")
    b.add_argument("--date-field", choices=["submitted", "updated"], default="submitted",
                   help="which date --from/--until filter on in seed mode: "
                        "submitted = original v1 date (default), updated = last metadata change")
    b.add_argument("--reprocess", action="store_true",
                   help="re-download papers already in the store "
                        "(default: skip them, so a resumed backfill is cheap)")
    b.add_argument("--concurrency", type=int, default=8,
                    help="parallel GCS downloads (default 8)")

    la = sub.add_parser("latest",
                        help="Part 1 (newest-first): most recent papers up to a size budget, "
                             "exact via GCS listing")
    la.add_argument("--seed-file", required=True,
                    help="Kaggle arXiv snapshot (.zip or .json) for the category filter")
    la.add_argument("--category-prefix", default=None,
                    help="primary-category prefix, e.g. cs.CL (omit for all categories)")
    la.add_argument("--max-gb", type=float, default=4.0, help="size budget (exact)")
    la.add_argument("--limit", type=int, default=None, help="optional cap on paper count")
    la.add_argument("--concurrency", type=int, default=8,
                    help="parallel GCS downloads (default 8)")

    sa = sub.add_parser("sample",
                        help="temporal sample: N papers per month across all years "
                             "(spans time so you can see trends, no embeddings)")
    sa.add_argument("--seed-file", required=True,
                    help="Kaggle arXiv snapshot (.zip or .json) for the category filter")
    sa.add_argument("--category-prefix", default=None,
                    help="primary-category prefix, e.g. cs.CL (omit for all categories)")
    sa.add_argument("--per-month", type=int, default=3,
                    help="papers to sample per month, spread evenly (default 3)")
    sa.add_argument("--from-year", type=int, default=None, help="earliest year (e.g. 2015)")
    sa.add_argument("--to-year", type=int, default=None, help="latest year")
    sa.add_argument("--max-gb", type=float, default=None, help="optional safety cap")
    sa.add_argument("--concurrency", type=int, default=8, help="parallel GCS downloads")

    dv = sub.add_parser("diverse",
                        help="diverse budget-bounded cs sample: per-month blended-facet "
                             "score spread across the distribution, facets stored per paper")
    dv.add_argument("--seed-file", required=True,
                    help="Kaggle arXiv snapshot (.zip or .json) for the category filter + facets")
    dv.add_argument("--category-prefix", default="cs",
                    help="category prefix (default cs; matches any listed category)")
    dv.add_argument("--per-month", type=int, default=20, help="papers per month (default 20)")
    dv.add_argument("--from-year", type=int, default=None, help="earliest year")
    dv.add_argument("--to-year", type=int, default=None, help="latest year")
    dv.add_argument("--max-gb", type=float, default=None, help="optional size cap")
    dv.add_argument("--concurrency", type=int, default=8, help="parallel GCS downloads")
    dv.add_argument("--citations-file", default=None,
                    help="internal-citations.json path or URL (default: GCS mirror, cached)")
    dv.add_argument("--core-file", default=None,
                    help="CORE rankings CSV path or URL for venue tiers (optional; "
                         "falls back to the curated top-venue set)")
    dv.add_argument("--weights", default=None,
                    help="override composite weights, e.g. "
                         "authority=0.3,niche=0.2,novelty=0.15,revisions=0.1,venue=0.25")

    u = sub.add_parser("update", help="RETIRED under D18 (OAI harvest banned); raises.")
    u.add_argument("--set", default="cs", help="OAI set / archive")
    u.add_argument("--category-prefix", default=None, help="narrow within the set, e.g. cs.CL")
    u.add_argument("--from", dest="frm", default=None,
                   help="override start date; default is last run's watermark")
    u.add_argument("--until", default=today(), help="end date YYYY-MM-DD")
    u.add_argument("--max-gb", type=float, default=None, help="optional safety cap")
    u.add_argument("--limit", type=int, default=None, help="optional safety cap")

    st = sub.add_parser("status", help="show store stats and the incremental watermark")

    sub.add_parser("reorganize",
                   help="move PDFs into pdfs/{YYYY}/{MM}/ year/month folders")

    args = p.parse_args(argv)

    if args.cmd == "reorganize":
        run_reorganize()
        return 0

    if args.cmd == "latest":
        run_latest(seed_file=args.seed_file, category_prefix=args.category_prefix,
                   max_gb=args.max_gb, limit=args.limit, concurrency=args.concurrency)
        return 0

    if args.cmd == "sample":
        run_sample(seed_file=args.seed_file, category_prefix=args.category_prefix,
                   per_month=args.per_month, concurrency=args.concurrency,
                   from_year=args.from_year, to_year=args.to_year, max_gb=args.max_gb)
        return 0

    if args.cmd == "diverse":
        cit = _ensure_local(args.citations_file or CITATIONS_URL,
                            DATA_DIR / "internal-citations.json")
        core = None
        if args.core_file:
            core = str(_ensure_local(args.core_file, DATA_DIR / "core-rankings.csv"))
        run_diverse(seed_file=args.seed_file, category_prefix=args.category_prefix,
                    per_month=args.per_month, max_gb=args.max_gb,
                    concurrency=args.concurrency, from_year=args.from_year,
                    to_year=args.to_year, citations_file=str(cit), core_file=core,
                    weights=parse_weights(args.weights))
        return 0

    if args.cmd == "status":
        conn = connect()
        papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        watermark = get_state(conn, "last_until")
        conn.close()
        # corpus size = actual PDFs on disk (the source of truth), YYMM subfolders
        pdfs = list(PDF_DIR.rglob("*.pdf")) if PDF_DIR.exists() else []
        disk = sum(p.stat().st_size for p in pdfs)
        years = len([d for d in PDF_DIR.iterdir() if d.is_dir()]) if PDF_DIR.exists() else 0
        print(f"papers:    {papers} rows indexed")
        print(f"corpus:    {len(pdfs)} PDFs across {years} year-folders, "
              f"{disk / 1024**3:.2f} GB in {PDF_DIR}")
        print(f"watermark: {watermark or '(never run)'}  <- next update starts here")
        return 0

    if args.cmd == "update":
        raise NotImplementedError(
            "update is retired under D18: it harvested OAI-PMH from "
            "export.arxiv.org, which no code path may touch. Refresh with a "
            "new Kaggle snapshot: backfill --seed-file <snapshot.zip> "
            "--source gcs-only --from <last-covered-date>."
        )

    frm = args.frm

    source = getattr(args, "source", "gcs-only")
    if source not in ("gcs", "gcs-only"):
        print(f"--source {source} is retired under D18; use gcs or gcs-only.",
              file=sys.stderr)
        return 1
    if not getattr(args, "seed_file", None):
        print("--source gcs needs --seed-file (the GCS path requires the version "
              "from metadata).", file=sys.stderr)
        return 1

    run(
        oai_set=args.set,
        frm=frm,
        until=args.until,
        max_gb=args.max_gb,
        limit=args.limit,
        category_prefix=args.category_prefix,
        seed_file=getattr(args, "seed_file", None),
        date_field=getattr(args, "date_field", "submitted"),
        # backfill skips papers already in the store (unless --reprocess).
        skip_existing=(args.cmd == "backfill" and not getattr(args, "reprocess", False)),
        source=source,
        concurrency=getattr(args, "concurrency", 1),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
