# arXiv full-text corpus collector

Free, no accounts. Discovers papers from the Kaggle metadata seed and
downloads the full-text PDFs from the free Google-hosted `arxiv-dataset`
mirror into nested `corpus/pdfs/{YYYY}/{MM}/`
year/month folders (e.g. `corpus/pdfs/2026/06/2606.27347.pdf`), recording one
metadata row per paper in a local SQLite index (`corpus/arxiv.db`) keyed by
`arxiv_id`. Under D18 no code path touches export.arxiv.org — there is no
OAI harvest and no arXiv scraper.

Code lives in `collector/`; every data artifact (PDFs, `arxiv.db`, caches, the
Kaggle seed `archive.zip`) lives in the repo-level `corpus/` directory
(gitignored). Paths in the collector resolve relative to its own location, so
commands work from `collector/` or via the root justfile.

**The corpus is the PDF files; the DB is just an index.** No text extraction or
chunking — if you want RAG later, run it over the collected PDFs then.

One job shares one pipeline:

- **Part 1 — backfill:** bulk pull from a date, capped by a size budget.
- **Part 2 — update:** RETIRED under D18 (it harvested OAI-PMH from
  export.arxiv.org). Refresh by re-running backfill with a newer snapshot:
  `backfill --seed-file <new-archive.zip> --source gcs-only --from <date>`.

## Quick start (just recipes)

The two parts are wired as [`just`](https://github.com/casey/just) recipes so
you don't have to remember flags. Run them from `collector/` (the repo-root
justfile delegates the common ones, e.g. `just status` works from the root too):

```bash
just setup             # uv-managed env + deps
just latest            # Part 1: newest papers up to 4 GB, exact (recommended)
just sample            # Part 1: a few papers per month across all years (trends)
just diverse           # Part 1: diverse spread across the impact/topic distribution
just seeded-backfill   # Part 1 alt: oldest-first from a start date
just status            # store stats + watermark
```

Downloads identify you in their User-Agent, as arXiv asks of automated users:
set `COLLECTOR_CONTACT_EMAIL` to your email first.

`backfill` aliases `seeded-backfill`.
Override any default inline, e.g. `just max_gb=8 category=cs.LG seeded-backfill`.
The raw CLI is documented below.

## Setup (manual)

Dependencies are declared in `pyproject.toml` and managed with
[`uv`](https://docs.astral.sh/uv/) (locked in `uv.lock`):

```bash
cd collector
uv sync
```

The raw CLI examples below assume this cwd (`collector/`); `uv run` uses the
managed environment (and syncs it automatically if missing).

## Part 1: get a large dataset (~4 GB to start)

### Recommended — `latest`: newest papers, exact budget

Walks backward from today and grabs the most recent papers up to `--max-gb`. It
uses the seed only for the **category filter** and the **GCS listing for exact
per-object sizes**, so it fills the budget precisely and downloads only the
selected PDFs (never non-matching categories).

```bash
uv run arxiv_ingest.py latest --seed-file ../corpus/archive.zip --category-prefix cs.CL --max-gb 4
```

- **Exact 4 GB** — sizes are known from the listing before anything downloads.
- **cs-only, no waste** — only the selected `cs.*` PDFs are fetched.
- **Parallel** — `--concurrency 8` (default) downloads 8 PDFs at once from GCS
  (workers fetch, one thread does all SQLite writes). GCS handles ~5000 reads/s,
  so you're bounded by your own bandwidth, not the mirror.
- Needs `--seed-file` (category lives only in metadata). Discovery scans the seed
  twice (~2 min of local parsing); the download phase dominates a real run.
- The mirror lags ~1 month, so "latest" means up to its newest month (currently
  ~late June 2026); newer weeks arrive with the next snapshot + mirror sync.

### `sample`: a few papers per month across all years (see trends)

Builds a corpus that **spans time** — `--per-month N` papers, evenly spread
within each month, for every month on the mirror. Small, but it lets you watch
how the field's titles/topics shift over the years without any embeddings.

```bash
uv run arxiv_ingest.py sample --seed-file ../corpus/archive.zip --category-prefix cs.CL --per-month 3
# bound the range or cap size:
uv run arxiv_ingest.py sample --seed-file ../corpus/archive.zip --category-prefix cs.CL \
    --per-month 5 --from-year 2015 --to-year 2026 --max-gb 2
```

View the trend straight from the index (no embeddings, just titles over time):

```bash
sqlite3 ../corpus/arxiv.db \
  "SELECT substr(published,1,7) AS month, arxiv_id, title
     FROM papers WHERE published != '' ORDER BY published;"
```

`sample` doesn't touch the backfill watermark (it's a spread, not a forward front).

### `diverse`: a diverse cs sample (blended-facet score)

Where `sample` spreads evenly by id, `diverse` spreads across the **impact/topic
distribution**. For each month it scores candidates on five self-contained
facets and takes `--per-month` papers spread across the blended score (not
top-K — spreading is what keeps it diverse), so the corpus deliberately spans
canonical, mid, and long-tail work instead of the newest slice only.

The five facets — also **stored per paper** (`authority`, `niche_idf`,
`author_novelty`, `revisions`, `venue_rigor`, `venue` columns) so a downstream
RAG can re-rank/filter on them at query time:

| facet | signal |
|---|---|
| `authority` | head: own citations (≤2015) / author authority (2016+) |
| `niche_idf` | tail: rarity of the paper's category tags (IDF) |
| `author_novelty` | emerging: fraction of authors new as of 2020 |
| `revisions` | maturity: version count |
| `venue_rigor` | rigor: 0–3 from venue extraction (+ optional CORE tiers) |

```bash
uv run arxiv_ingest.py diverse --seed-file ../corpus/archive.zip --category-prefix cs \
    --per-month 20 --max-gb 8
# tune the blend, bound the range, add CORE venue tiers:
uv run arxiv_ingest.py diverse --seed-file ../corpus/archive.zip --category-prefix cs \
    --per-month 20 --from-year 2010 --to-year 2026 \
    --weights authority=0.3,niche=0.2,novelty=0.15,revisions=0.1,venue=0.25 \
    --core-file core-rankings.csv
```

It is **self-contained**: besides the seed, the only extra fetch is the frozen
`internal-citations.json` (~172 MB, cached under `corpus/data/`). The facet table takes
~2–3 min to build on the first run and is cached (keyed by input mtimes).

Two honest limits, both documented in the design spec:
- Citations are frozen ~early 2020, so `authority` uses each paper's own
  citations up to 2015 and its authors' reputation after; recent months lean on
  the other facets.
- `venue_rigor` is **positive-only** — only ~36–45% of cs papers expose a venue
  in metadata (declining over time), so absence means "undetected", never
  "unpublished". The run prints a `venue_rigor` histogram of the selection.

`diverse` doesn't touch the backfill watermark either.

### Alternative — `backfill`: oldest-first from a start date

Same GCS mirror, but fills the budget from `--from` **forward** (earliest first).
Use when you want a specific historical window rather than the newest papers.

#### Kaggle seed + GCS mirror (fast, free, unthrottled)

Download the [arXiv dataset](https://www.kaggle.com/datasets/Cornell-University/arxiv)
(`archive.zip`, ~1.7 GB) and place it at `corpus/archive.zip`. Ids + metadata
(incl. the latest version) are streamed
straight out of the zip; PDFs come from the free Google-hosted mirror
(`storage.googleapis.com/arxiv-dataset`, ~11 MB/s, no rate limit, no auth).

```bash
uv run arxiv_ingest.py backfill --seed-file ../corpus/archive.zip --source gcs \
    --category-prefix cs.CL --from 2024-01-01 --max-gb 4
```

- `--source gcs` (the default) needs `--seed-file` — the mirror is keyed by
  month, so it uses the id + version from the metadata to build the exact object
  path `.../pdf/{YYMM}/{id}v{N}.pdf`.
- `--from/--until` filter on the **original submission date** by default
  (`--date-field submitted`); use `--date-field updated` for last-metadata-change.
  Both dates are stored (`published` vs `datestamp`), as is the fetched `version`.
- Only new-style ids (`2401.00003`) map to the mirror; pre-2007 ids
  (`hep-th/9901001`) are logged and skipped. If a very recent paper isn't
  mirrored yet, it is skipped — it lands with the next mirror sync.

#### OAI / arXiv scraper lanes (RETIRED under D18)

The `--source arxiv` scraper fallback and the seedless OAI-crawl discovery are
retired: no code path may touch export.arxiv.org. The stubs raise
`NotImplementedError` naming the ban. Refresh cadence is a new Kaggle snapshot
plus a mirror pull, not an incremental crawl.

Re-running resumes cheaply: papers already in the store are
skipped entirely (no re-download). Pass `--reprocess` to force re-download.

## Part 2: incremental updates (RETIRED under D18)

`update` harvested OAI-PMH from export.arxiv.org and is retired with it —
the command raises `NotImplementedError`. To refresh, pull a newer Kaggle
snapshot and re-run backfill from the last covered date (already-stored
papers skip, so it acts as the forward front):

```bash
uv run arxiv_ingest.py backfill --seed-file ../corpus/archive.zip --source gcs-only \
    --category-prefix cs.CL --from 2026-08-23 --max-gb 4
```

The `last_until` watermark is still written by backfill runs and shown by
`status`, as a record of the covered window.

## Inspect

```bash
uv run arxiv_ingest.py status
sqlite3 ../corpus/arxiv.db "SELECT arxiv_id, version, size_bytes, title FROM papers LIMIT 5;"
ls ../corpus/pdfs/                    # year folders: 2007/ ... 2026/
ls ../corpus/pdfs/2026/06/ | head     # the corpus itself
```

PDFs are organized as `corpus/pdfs/{YYYY}/{MM}/{id}.pdf`. `uv run arxiv_ingest.py
reorganize` migrates any older layout (flat or `{YYMM}/`) into place — it's
idempotent and layout-agnostic.

## Schema

- `papers(arxiv_id PK, title, authors, abstract, categories, datestamp, published, version, pdf_path, size_bytes, fetched_at, authority, niche_idf, author_novelty, revisions, venue_rigor, venue)`
  - `published` = original v1 submission date; `datestamp` = when arXiv last touched the record; `version` = PDF version fetched (e.g. `v4`, GCS path only); `pdf_path`/`size_bytes` point at the downloaded file
  - `authority`, `niche_idf`, `author_novelty`, `revisions`, `venue_rigor`, `venue` = per-paper facets from the `diverse` sampler (NULL for other modes) — see the [diverse-sample design spec](../docs/superpowers/specs/2026-07-03-diverse-cs-sample-design.md)
- `ingest_state(key, value)` — holds the incremental `last_until` watermark

The PDFs in `corpus/pdfs/` are the deliverable; the table is an index over them. Turning
this into a RAG system (extract → chunk → embed → vector store) is deliberately
out of scope — run that over the collected PDFs separately.
