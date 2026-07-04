# arXiv full-text corpus collector

Free, no accounts. Discovers papers (Kaggle metadata seed or arXiv's OAI-PMH
feed) and downloads the full-text PDFs (free Google-hosted `arxiv-dataset`
mirror, or the `export.arxiv.org` scraper) into nested `pdfs/{YYYY}/{MM}/`
year/month folders (e.g. `pdfs/2026/06/2606.27347.pdf`), recording one metadata
row per paper in a local SQLite index (`arxiv.db`) keyed by `arxiv_id`.

**The corpus is the PDF files; the DB is just an index.** No text extraction or
chunking — if you want RAG later, run it over the collected PDFs then.

Two jobs share one pipeline:

- **Part 1 — backfill:** bulk historical pull, capped by a size budget.
- **Part 2 — update:** incremental pull of everything with a datestamp since the
  last run, upserting by id (idempotent).

## Quick start (just recipes)

The two parts are wired as [`just`](https://github.com/casey/just) recipes so
you don't have to remember flags:

```bash
just setup             # venv + deps
just latest            # Part 1: newest papers up to 4 GB, exact (recommended)
just sample            # Part 1: a few papers per month across all years (trends)
just diverse           # Part 1: diverse spread across the impact/topic distribution
just seeded-backfill   # Part 1 alt: oldest-first from a start date
just oai-backfill      # Part 1 fallback: OAI crawl + arXiv scraper (rate-limited)
just oai-update        # Part 2: incremental pull via OAI-PMH
just status            # store stats + watermark
```

`backfill` aliases `seeded-backfill` and `update` aliases `oai-update`.
Override any default inline, e.g. `just max_gb=8 category=cs.LG seeded-backfill`.
The raw CLI is documented below.

## Setup (manual)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Part 1: get a large dataset (~4 GB to start)

### Recommended — `latest`: newest papers, exact budget

Walks backward from today and grabs the most recent papers up to `--max-gb`. It
uses the seed only for the **category filter** and the **GCS listing for exact
per-object sizes**, so it fills the budget precisely and downloads only the
selected PDFs (never non-matching categories).

```bash
python arxiv_ingest.py latest --seed-file archive.zip --category-prefix cs.CL --max-gb 4
```

- **Exact 4 GB** — sizes are known from the listing before anything downloads.
- **cs-only, no waste** — only the selected `cs.*` PDFs are fetched.
- **Parallel** — `--concurrency 8` (default) downloads 8 PDFs at once from GCS
  (workers fetch, one thread does all SQLite writes). GCS handles ~5000 reads/s,
  so you're bounded by your own bandwidth, not the mirror. Only the arXiv scraper
  path stays single-connection (its rate limit requires it).
- Needs `--seed-file` (category lives only in metadata). Discovery scans the seed
  twice (~2 min of local parsing); the download phase dominates a real run.
- The mirror lags ~1 month, so "latest" means up to its newest month (currently
  ~late June 2026); the truly-current week is `update`'s job.

### `sample`: a few papers per month across all years (see trends)

Builds a corpus that **spans time** — `--per-month N` papers, evenly spread
within each month, for every month on the mirror. Small, but it lets you watch
how the field's titles/topics shift over the years without any embeddings.

```bash
python arxiv_ingest.py sample --seed-file archive.zip --category-prefix cs.CL --per-month 3
# bound the range or cap size:
python arxiv_ingest.py sample --seed-file archive.zip --category-prefix cs.CL \
    --per-month 5 --from-year 2015 --to-year 2026 --max-gb 2
```

View the trend straight from the index (no embeddings, just titles over time):

```bash
sqlite3 arxiv.db \
  "SELECT substr(published,1,7) AS month, arxiv_id, title
     FROM papers WHERE published != '' ORDER BY published;"
```

`sample` doesn't touch the `update` watermark (it's a spread, not a forward front).

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
python arxiv_ingest.py diverse --seed-file archive.zip --category-prefix cs \
    --per-month 20 --max-gb 8
# tune the blend, bound the range, add CORE venue tiers:
python arxiv_ingest.py diverse --seed-file archive.zip --category-prefix cs \
    --per-month 20 --from-year 2010 --to-year 2026 \
    --weights authority=0.3,niche=0.2,novelty=0.15,revisions=0.1,venue=0.25 \
    --core-file core-rankings.csv
```

It is **self-contained**: besides the seed, the only extra fetch is the frozen
`internal-citations.json` (~172 MB, cached under `data/`). The facet table takes
~2–3 min to build on the first run and is cached (keyed by input mtimes).

Two honest limits, both documented in the design spec:
- Citations are frozen ~early 2020, so `authority` uses each paper's own
  citations up to 2015 and its authors' reputation after; recent months lean on
  the other facets.
- `venue_rigor` is **positive-only** — only ~36–45% of cs papers expose a venue
  in metadata (declining over time), so absence means "undetected", never
  "unpublished". The run prints a `venue_rigor` histogram of the selection.

`diverse` doesn't touch the `update` watermark either.

### Alternative — `backfill`: oldest-first from a start date

Same GCS mirror, but fills the budget from `--from` **forward** (earliest first).
Use when you want a specific historical window rather than the newest papers.
Two independent choices: **id discovery** (Kaggle seed vs. OAI crawl) and
**PDF source** (`--source gcs` vs. `--source arxiv`).

#### Kaggle seed + GCS mirror (fast, free, unthrottled)

Download the [arXiv dataset](https://www.kaggle.com/datasets/Cornell-University/arxiv)
(`archive.zip`, ~1.7 GB). Ids + metadata (incl. the latest version) are streamed
straight out of the zip; PDFs come from the free Google-hosted mirror
(`storage.googleapis.com/arxiv-dataset`, ~11 MB/s, no rate limit, no auth).

```bash
python arxiv_ingest.py backfill --seed-file archive.zip --source gcs \
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
  mirrored yet, it falls back to the arXiv scraper for that one file.

#### arXiv scraper fallback (`--source arxiv`, rate-limited)

For when you can't get the Kaggle file, or want live OAI discovery:

```bash
# no seed: crawl OAI-PMH for ids, scrape PDFs from export.arxiv.org
python arxiv_ingest.py backfill --set cs --source arxiv \
    --category-prefix cs.CL --from 2024-01-01 --max-gb 4
```

arXiv asks for **1 request / 3s, single connection**, and actively throttles
bulk PDF scraping (2026: frequent `429`s and mid-stream connection resets). So
this path paces every request (3s min + jitter) and uses exponential backoff
(`3→6→12→24→48s`) on `429`/`503`/connection errors. It works, but it's slow and
against arXiv's guidance for bulk — prefer the GCS mirror.

Re-running resumes cheaply on either path: papers already in the store are
skipped entirely (no re-download). Pass `--reprocess` to force re-download.

## Part 2: incremental updates

```bash
# Fetch everything arXiv touched since the last run's watermark, upsert by id.
python arxiv_ingest.py update --set cs

# Run it daily (cron / launchd):
# 0 6 * * *  cd /Users/nabin/projects/rags && .venv/bin/python arxiv_ingest.py update --set cs
```

The watermark (`last_until`) is stored in the DB, so `update` is idempotent and
picks up where the last run left off. Note: the OAI datestamp reflects when
arXiv last touched a record, so *newly submitted* papers flow in, but this demo
does not re-fetch historical papers whose content changed long ago — by design.

## Inspect

```bash
python arxiv_ingest.py status
sqlite3 arxiv.db "SELECT arxiv_id, version, size_bytes, title FROM papers LIMIT 5;"
ls pdfs/                    # year folders: 2007/ ... 2026/
ls pdfs/2026/06/ | head     # the corpus itself
```

PDFs are organized as `pdfs/{YYYY}/{MM}/{id}.pdf`. `python arxiv_ingest.py
reorganize` migrates any older layout (flat or `{YYMM}/`) into place — it's
idempotent and layout-agnostic.

## Schema

- `papers(arxiv_id PK, title, authors, abstract, categories, datestamp, published, version, pdf_path, size_bytes, fetched_at, authority, niche_idf, author_novelty, revisions, venue_rigor, venue)`
  - `published` = original v1 submission date; `datestamp` = when arXiv last touched the record; `version` = PDF version fetched (e.g. `v4`, GCS path only); `pdf_path`/`size_bytes` point at the downloaded file
  - `authority`, `niche_idf`, `author_novelty`, `revisions`, `venue_rigor`, `venue` = per-paper facets from the `diverse` sampler (NULL for other modes) — see the [diverse-sample design spec](docs/superpowers/specs/2026-07-03-diverse-cs-sample-design.md)
- `ingest_state(key, value)` — holds the incremental `last_until` watermark

The PDFs in `pdfs/` are the deliverable; the table is an index over them. Turning
this into a RAG system (extract → chunk → embed → vector store) is deliberately
out of scope — run that over the collected PDFs separately.
