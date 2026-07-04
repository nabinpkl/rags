# Diverse cs sample — design

Date: 2026-07-03
Status: approved for planning

## Goal

Produce a **diverse, budget-bounded sample of cs papers** spanning the full arXiv
timeline (2007-04 → present) and the impact/topic distribution — *without*
downloading the full cs corpus. The sample feeds a downstream RAG, so alongside
the PDFs we persist **per-paper facet metadata** that the retriever can re-rank
or filter on at query time.

The core realization driving this design: the sampling "strata" we kept adding
(canonical, emerging, niche, …) are **retrieval facets**. Freezing them into
fixed download quotas does not scale — there is always one more facet. So facets
become (a) *terms in a blended score* used for selection and (b) *columns of
metadata* the RAG uses later. Selection is one tunable score, not N buckets.

## Non-goals

- Not the full corpus; `--max-gb` bounds it.
- No embeddings / semantic clustering. All signals are count-based and
  self-contained. (Semantic topic communities are explicitly out of scope — see
  Caveats.)
- No **live** external APIs (OpenAlex/Semantic Scholar/CORE portal queries).
  Static reference files that are downloaded once and cached
  (`internal-citations.json`, the CORE rankings CSV) are allowed — same pattern,
  no per-query network, no ban surface.
- Not a currency/update mechanism. This shapes the corpus; `update` keeps it
  current. `diverse` does **not** touch the `last_until` watermark.

## Data sources (all already available)

1. **Seed** (`archive.zip`, Kaggle `arxiv-metadata-oai.json`, streamed from the
   zip; runs to the snapshot date ~2026-06). Per record we use:
   `id`, `categories`, `authors_parsed`, `abstract`, `journal-ref`, `doi`,
   `comments`, `versions`, dates. Verified present in the snapshot.
2. **`internal-citations.json`** (GCS `metadata-v5/`, ~172 MB, **frozen ~early
   2020**). Forward map `citing_id → [cited_id, …]`. Inverted to per-paper
   in-degree. This is the only extra file we fetch.
3. **GCS month listing** (`arxiv/arxiv/pdf/{YYMM}/`) — authoritative per-object
   `size` and version, as already used by `run_latest`/`run_sample`.
4. **CORE conference rankings CSV** (downloaded once, cached like the citations
   file) → `venue → tier` (A*/A/B/C). Conferences only; a small curated
   journal-tier list (JMLR, TACL, TPAMI, JACM, CACM, TON, TOG, …) complements it.

`authors-parsed.json` on GCS is **not** used — the seed's `authors_parsed`
covers all years and gives one consistent author-key normalization.

## Lookup tables (built once, cached)

Built during setup, then pickled to a cache keyed by `(seed mtime, citations
file mtime)` so re-runs skip the expensive parse.

**A. Citation in-degree** — `indeg: id → int`
Stream `internal-citations.json`; for each `citing → [cited…]`, increment
`indeg[cited]`. Covers pre-2020 papers (the file's horizon).

**B. Author authority** — `author_authority: author_key → int`
Stream the seed; for each **pre-2020** paper, add `indeg[id]` to each of its
authors' running totals. `author_key = f"{last}|{first_initial}".lower()`
(last name + first initial — a deliberate balance between collision and
fragmentation; imperfect, see Caveats). Also record the set of pre-2020 author
keys (for novelty).

**C. Category IDF** — `cat_idf: tag → float`
In the same seed pass, count document frequency `df[tag]` over all cs papers
(a paper counts for every category tag it carries). With `N` = number of cs
papers, `cat_idf[tag] = log(N / df[tag])`. This is the global, stable reference
that makes "niche" a measured quantity rather than an opinion.

## Per-paper facets (computed for every candidate, stored on every ingested row)

| facet | definition | axis |
|---|---|---|
| `authority` | year ≤ 2015: `indeg[id]` (own citations). year ≥ 2016: `max` over the paper's authors of `author_authority[key]` (has a heavyweight). | head / canonical |
| `niche_idf` | `max` over the paper's category tags of `cat_idf[tag]`. | tail / topic |
| `author_novelty` | fraction of the paper's authors absent from the pre-2020 author-key set (a "new to the field as of 2020" team). ~0 for old papers by construction; discriminates recent papers, which is its purpose. | emerging |
| `revisions` | version count of the mirrored PDF (from the GCS listing). No citation lag. | maturity |
| `venue_rigor` | graded 0–3 from venue extraction + CORE/journal tier lookup (see Venue rigor). Also stores the extracted `venue` string. **Positive-only** — absence means "undetected", not "unpublished". | rigor / quality |

The `authority` `≤2015 / ≥2016` split is the agreed cutover: by the 2020 freeze,
≤2015 papers had ≥5 years to accrue citations (own in-degree reliable); 2016+
own-citations are lag-starved, so authority routes through author reputation
instead. Months never straddle the boundary (we process per month), so the two
scales never mix within a normalization pool.

## Venue rigor

**Measured reality (full seed, 967k cs papers)** — venue signal is sparse and
*declines* over time, so recall (not ranking) is the binding constraint:

| era | cs papers | doi% | jref% | comments% | ANY% |
|---|---|---|---|---|---|
| ≤2015 | 105k | 24.9 | 25.2 | 16.9 | 44.8 |
| 2016–2019 | 158k | 21.1 | 14.6 | 23.0 | 42.2 |
| 2020+ | 703k | 13.9 | 9.2 | 24.3 | 36.0 |

Consequences that shape the design:
- **Positive-only signal.** Only ~36–45% of cs papers have any detectable venue,
  yet most of the undetected ones *are* published (authors don't backfill arXiv).
  So `venue_rigor` marks verified-rigorous papers; it **must not** be used to
  exclude the rest.
- **Recent cs detection is comments-driven** (the noisy source), so parsing
  requires an **acceptance cue** (`accepted | to appear | camera-ready |
  proceedings | published in`) *near* a venue token — not a bare mention — to
  avoid false positives ("rejected from ICML").
- The detectable slice is **biased** toward annotating authors and
  journal-heavy subfields; label it honestly as "verifiably published at a
  ranked venue", not "all rigorous papers".

**Extraction** (best precision first): **DOI prefix** (`10.18653`=ACL,
`10.1109`=IEEE, `10.1145`=ACM, `10.1103`=APS, `10.1038`=Nature, …) → **journal-ref**
regex → **comments** (acceptance-cue + venue token).

**Tiering**: map the extracted venue against the cached **CORE rankings** CSV
(conferences, A*/A/B/C) plus a small curated **journal-tier** list. Grade:
`3` = top-tier (CORE A*/A or top journal), `2` = ranked venue (B/C or recognised
journal), `1` = published-generic (DOI/journal-ref present, venue not resolved),
`0` = none detected.

**Selection role**: `venue_rigor` is a **weighted composite term** (below), not a
reserved bucket — consistent with the blended-score decision. The integration
run reports the rigorous representation of the sample; if the spread starves it,
escalate to a single small `--rigorous-quota` (default 0). Term-first,
quota-only-if-measured-starved.

## Scoring and selection

Per month, over candidates that (a) are cs, (b) are not already ingested
(idempotent top-up), and (c) pass a light anti-junk floor
(`abstract` non-empty **and** PDF size ≥ ~50 KB):

1. **Rank-normalize** each facet to `[0,1]` within the month's candidate pool
   (rank-normalization is robust to the heavy-tailed raw distributions).
2. **Composite** = weighted sum. Default weights (tunable via `--weights`):
   `authority 0.30, niche_idf 0.20, author_novelty 0.15, revisions 0.10,
   venue_rigor 0.25`.
3. **Select by spread, not by top-K.** Take `_even_sample(sorted_by_composite,
   per_month)` — the existing helper — so the picks **span** canonical → mid →
   tail instead of collapsing onto one end. This is the crux: a scalar score has
   a single optimum, so `argmax`/top-K would defeat diversity; spreading across
   the score is what makes the sample diverse.

Every selected paper stores its five facet values (raw) as columns, regardless
of why it was picked — that is the query-time faceting layer.

## Budget, ordering, idempotency

- Primary control: `--per-month K`. Temporal diversity is structural (every
  month folder is visited).
- `--max-gb` is an optional hard cap, exact via GCS sizes. When set, months are
  processed chronologically until the cap; a tight budget therefore truncates
  the newest months. Known limitation — for guaranteed temporal spread under a
  tight budget, size `per_month` to the budget rather than relying on the cap.
- `--from-year` / `--to-year` restrict the month range.
- Idempotent: already-ingested ids are skipped and count toward the per-month
  floor, so re-runs top up rather than re-selecting.
- Download via the existing concurrent `_download_selected` (workers fetch from
  GCS, one thread upserts).

## Storage / schema

Add nullable columns to `papers`: `authority REAL`, `niche_idf REAL`,
`author_novelty REAL`, `revisions INTEGER`, `venue_rigor INTEGER`, `venue TEXT`.
Guarded `ALTER TABLE … ADD COLUMN` (skip if the column exists) so the migration
is idempotent. Extend `upsert_paper` to write them.

## CLI

```
python arxiv_ingest.py diverse \
    --seed-file archive.zip \
    --category-prefix cs \
    --per-month 20 \
    --max-gb 8 \
    --concurrency 8 \
    [--from-year 2007] [--to-year 2026] \
    [--citations-file <path-or-url>] [--core-file <path-or-url>] \
    [--rigorous-quota 0] \
    [--weights authority=0.30,niche=0.20,novelty=0.15,revisions=0.10,venue=0.25]
```

`--citations-file` and `--core-file` default to their source URLs; each is
downloaded once and cached locally (`data/internal-citations.json`,
`data/core-rankings.csv`) so re-runs skip the fetch. `--rigorous-quota` defaults
to 0 (venue rigor is a weighted term); set it only if the integration run shows
the rigorous slice starved. `diverse` supersedes `sample` (which is `diverse`
with only an even-spread term); `sample` is retained for now.

## Reuse

Same skeleton as `run_sample` / `run_latest`: seed scan → walk months → per-month
select → `_download_selected`. New machinery only:
- the lookup tables (in-degree inversion, author authority, category IDF, CORE
  venue→tier),
- venue extraction (DOI-prefix + journal-ref + comments),
- the per-paper facet computation + composite scoring,
- the schema columns.
`_even_sample`, `gcs_months`, `gcs_month_objects`, `_download_selected`,
`seed_records` are reused as-is (with `seed_records` extended to surface
`authors_parsed`, `journal-ref`, `doi`, `comments`).

## Honest caveats (documented, all degrade soft)

- **Authority frozen at 2020** — misses researchers who rose 2021-2026; biased
  toward established names, worsening for the newest months. The `author_novelty`
  term partially compensates by lifting new teams.
- **Author disambiguation is imperfect** — `last|first_initial` collides on
  common names (notably cs.CL's Chinese-name overlap) and can fragment. `max`
  aggregation at the paper level limits the damage; a bad key inflates at most
  one paper's authority, not a quota.
- **Niche is category-level only** — captures cross-field / rare-subfield
  marginality, not intra-field topic communities (two cs.CL papers look
  identical to the taxonomy). Finer resolution needs term-IDF or embeddings;
  out of scope.
- **Citation/authority understated 2016-2019** (lag at the 2020 freeze).
- **Venue rigor is positive-only and low-recall** — ~36–45% of cs papers have any
  detectable venue, declining over time; the rigorous slice is biased toward
  annotating authors / journal-heavy subfields, and recent-cs detection relies on
  noisy `comments` parsing. Never used to exclude, only to mark. (See Venue rigor.)
- **Single-axis composite spread approximates multi-facet diversity.** Spreading
  across one blended axis is not the same as covering every facet's range
  (true multi-facet coverage = MMR/facility-location); accepted for the MVP,
  since the blended-score decision explicitly traded guaranteed quotas for scale.
- **Budget vs temporal coverage** — a tight `--max-gb` truncates newest months
  (see Budget).

## Testing

- Unit: category IDF math; in-degree inversion on a small fixture; author-authority
  aggregation + key normalization; novelty fraction; venue extraction
  (DOI-prefix, journal-ref, comments acceptance-cue) + CORE tier lookup +
  false-positive cases ("rejected from ICML"); composite rank-normalization;
  `_even_sample` (already covered).
- Integration: `diverse --category-prefix cs --per-month 3 --max-gb 0.1` against
  live GCS — assert facet columns are populated, the sample spans multiple
  months, sizes stay under the cap, a second run is a no-op (idempotency), and
  **report the venue_rigor distribution** of the selection (to decide whether the
  rigorous slice needs a quota).

## Build order

1. Schema migration + `upsert_paper` columns.
2. Extend `seed_records` to surface `authors_parsed`, `journal-ref`, `doi`,
   `comments`.
3. Lookup tables + disk cache (in-degree, author authority, category IDF, CORE
   venue→tier).
4. Venue extraction (DOI-prefix + journal-ref + comments) → `venue_rigor`.
5. Per-paper facet computation + composite + rank-normalization + spread select.
6. `run_diverse` wiring + CLI subcommand (incl. `--core-file`, `--rigorous-quota`).
7. Tests (unit, then a small live integration run that reports the venue_rigor
   distribution).
8. justfile recipe + README section.
