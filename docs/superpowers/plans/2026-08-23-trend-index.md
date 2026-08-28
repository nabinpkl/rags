# Trend index — metadata parity with arXiv, and trends that are queries, not claims

Status: **proposal**, 2026-08-23, owner-directed priority ("first is freshness
index parity so a trend site can be generated irrespective of agent and
RAG"). Supersedes the ordering in `2026-08-23-freshness.md` (full-text
deltas) and `2026-08-23-corpus-pulse.md` (dashboard): both still apply, but
they sit *on top of* this layer instead of being the source of freshness.

## 0. Why this comes first

Everything "fresh" in the earlier plans was gated by full text: PDFs →
extraction → embedding (9 h/month on this CPU, 188 h for the backlog). But
the signal a trend site needs — title, abstract, categories, dates,
versions, license — is **metadata, which arXiv publishes as CC0** (§6b
item 5), weighs ~1.5 KB a paper, and needs no LLM, no GPU, no budget cap.
A metadata index can sit at parity with arXiv (≤ 7 days behind) for the
cost of a weekly download. The RAG corpus then becomes what it honestly
is: *the sample of that catalog we can deep-read*, linked by `arxiv_id`.

Measured scale (2026-08-23, Kaggle seed + Google mirror):

| scope | papers, all time | per month now | metadata size |
|---|---|---|---|
| cs.CL-primary | 83,362 | ~1.6k | ~150 MB with abstracts |
| cs.CL anywhere in categories | 111,656 | ~2.5k | ~200 MB |
| cs.* primary | 772,337 | ~17k | ~1.3 GB |
| all arXiv | 3,087,072 | ~30k | 5 GB (the seed itself) |

Sources and their lag:

| source | carries | cadence | lag | cost |
|---|---|---|---|---|
| Kaggle `arxiv-metadata-oai-snapshot` | everything incl. license, versions, journal-ref, doi, comments | weekly republish | ~1 week | 1.7 GB download |
| OAI-PMH `arXiv` format (export.arxiv.org) | title/abstract/authors/categories/created/datestamp (+ `<license>` if parsed) | live | hours | paced 3 s/page, 1–2k records/page → a cs.CL week is ~2 pages |
| Google mirror listing | ids, versions, PDF sizes, sync date | Sunday batches, 1–2 weekly | 1–2 weeks | free |

Parity recipe: **Kaggle weekly as the base** (one deterministic rebuild)
**+ OAI for the days since the seed** (cheap, closes the gap to < 1 day
when wanted). The mirror listing is only consulted by the full-text delta.

## 1. The liability problem, and the rule that answers it

"Bucketing a trend is a liability hazard." Concretely: an aggregate like
"agentic workflows up 129 %" invites three failures — the bucket is wrong
(keyword ≠ topic), a paper is in the wrong bucket, or the number is
presented as an editorial finding nobody can check. The market's trend
reports do exactly this (§4: aggregate-only, no drill-down).

**Rule: a trend is a saved query, and the page shows the query's result
set, not a conclusion about it.** Every number on the site is
`count(papers where <rule>) per month`, where `<rule>` is a literal,
displayed matching rule over CC0 fields (e.g. *title or abstract contains
"state space model" or "Mamba", primary category cs.CL*). Clicking any
point expands to that month's matching papers, each a link to
`arxiv.org/abs/<id>`. The permalink encodes the rule, so anyone can
reproduce the number and anyone can flag it.

What this rules out, deliberately:

- **No LLM-written trend narrative** in v1. Labels are the matched terms
  themselves. (If an AI summary is ever layered on, it follows the
  existing §6c posture: labeled AI-generated, cites ids.)
- **No social/popularity signal** — no upvotes, no X/HN mentions, no
  "hot". Those are other people's products (§4) and a ranking we cannot
  source.
- **No invented topic names.** If clustering is added (phase 5), a
  cluster is named by its top matched terms and shown with its members,
  never by a generated title.
- **No affiliation/institution claims** — arXiv metadata has no
  affiliations; anything institutional would be inference, so it is out.

And what it requires on every surface:

- The matching rule, verbatim, next to every chart.
- The denominator, stated: "share of cs.CL papers that month" vs absolute
  count, both available, default = share (the field grew ~25 %/yr; raw
  counts mislead).
- The catalog stamp: "catalog current to 2026-08-21 (Kaggle snapshot
  2026-08-16 + OAI to 2026-08-21)" on the page, not in a footer.
- **Flag this** on every series and every paper row. No accounts, no
  write path (D4/D11): the button opens a pre-filled GitHub issue in the
  public repo carrying the permalink, the rule, and the paper id, with
  three fixed reasons — *rule matches the wrong thing*, *this paper
  doesn't belong here*, *remove my paper from the trend index*. The
  third is honoured by an exclusion list the builder applies
  (mirrors §6c's takedown path). Flags are public, so the fix is public.
- A methodology page: the counting rule, what "cs.CL" means here
  (primary vs any-listed, stated), known failure modes (keyword ≠ topic;
  abstracts only; new terms take months to be used consistently), and
  the seed/OAI provenance.

## 2. Architecture (additive, read-only in serving)

```
 Kaggle seed (weekly) ─┐
                       ├─► catalog builder ─► catalog.db  (papers, FTS5 title+abstract)
 OAI delta (days) ─────┘          │
                                  ▼
                      trend builder (SQL + n-gram mining) ─► trends.db
                                  │                           (series, emerging, denominators)
                                  ▼
            FastAPI  GET /api/trends/…  (reads both, mode=ro)  ─►  /trends page
                                  │
 corpus.db (RAG, unchanged) ◄── join on arxiv_id: "deep-readable" badge, open in viewer
```

- **`catalog.db`** — new SQLite, same D4 posture as `corpus.db`: built
  offline to a tmp file, renamed, bind-mounted `:ro`. Tables: `papers`
  (id, title, abstract, authors, categories, primary_category, published,
  updated, latest_version, license, journal_ref, doi, comments,
  source = kaggle|oai, seed_snapshot), `papers_fts` (title, abstract),
  `meta` (seed date, oai watermark, built_at), `exclusions` (ids removed
  on request, with the issue number). Scope v1: **cs.CL anywhere in
  categories** (111k rows, ~200 MB) with `primary_category` kept so the
  UI can default to primary. `cs.*` is a one-flag change later; the
  builder is scope-agnostic.
- **`trends.db`** — derived, rebuilt whole each run (minutes): `series`
  (rule_id, month, n, denominator), `rules` (rule_id, label, match spec
  JSON, origin = curated|mined), `emerging` (rule_id, window, share_now,
  share_before, support). Two rule origins: a **curated list** in
  `trends/vocabulary.py` (literal dict, reviewed in PRs — the only place
  editorial judgement enters, and it is diffable) and **mined n-grams**
  (1–3-grams from titles/abstracts, min support ≥ 20 papers/month,
  stopworded, stemmed) that surface terms nobody curated. Mined rules
  are labeled "mined" in the UI.
- **API** (`askrag/api/routes_trends.py`, `askrag/trends/*.py`, tests
  1:1): `GET /api/trends/series?rule=…&from=…&to=…&normalize=share|count`,
  `GET /api/trends/emerging?window=6m`, `GET /api/trends/papers?rule=…
  &month=…&cursor=…` (the drill-down — paginated, title/authors/abstract/
  abs-link, plus `in_corpus` from the `corpus.db` join), `GET /api/trends/
  meta` (stamps, scope, exclusion count). Rules arrive as ids or as a
  validated match spec (enum'd ops: `term_in_title_or_abstract`,
  `primary_category`, `any_category`, `year_range`) — the same enum
  discipline as `query_metadata`, no free text reaching SQL except as an
  FTS5 MATCH argument that we quote.
- **Frontend**: a second static page `/trends` (Next static export;
  §4c's "one shell" applies to the explorer/viewer/agent app, this is a
  sibling page, recorded as a decision). Series chart (one rule, or
  compare up to 4), emerging list, a category/cross-list panel, and the
  drill-down drawer. The `/` app gains one link.
- **Builder schedule**: weekly host timer, Sunday night after the mirror
  sync; runs `just catalog-refresh` = download seed if newer → build
  catalog → OAI top-up → build trends → validate (row count ≥ previous,
  stamps advance) → atomic rename → API picks it up on next open (or a
  container restart if the mount is a file: use a directory mount with
  `current/` symlink, same convention as the freshness plan). No
  embeddings, no key, no LLM: D12's reasons for rejecting a VPS job do
  not apply, but D12 still gets an amendment saying exactly that.

## 3. Build order

1. **Catalog builder + parity check** (`catalog/` — seed reader reused
   from the collector's `seed_records`, OAI reader reused from `harvest`,
   new `build_catalog.py`, `just catalog-status` printing "current to
   <date>, N papers, lag D days"). Acceptance: rebuild from a fresh seed
   in < 10 min on the host; lag ≤ 7 days after a run.
2. **Trend builder** with the curated vocabulary (~40 rules to start:
   architectures, training methods, eval themes, data themes, the model
   families people actually track) + mined n-grams. Acceptance: every
   series reproducible by a one-line SQL shown on the methodology page;
   `emerging` excludes anything with support < 20.
3. **API + tests**, including the flag-link builder (pure function → URL)
   and the exclusion list applied at build.
4. **`/trends` page**: chart, drill-down, permalinks, flag buttons,
   methodology, catalog stamp. Phone first (the pulse-plan container-query
   rule applies).
5. **Weekly timer + docs + decisions** (D17 catalog layer; D12 amendment;
   §2 product shape gains the trend surface; `.claude/rules` note that
   trend rules are data in `vocabulary.py`, never prose in components).
6. Later, separately decided: abstract-embedding clusters (CPU-feasible:
   111k abstracts ≈ one day once, minutes weekly); citation counts from
   OpenAlex (CC0) as a second, sourced signal; letting the explorer browse
   the catalog (a D16 change — not assumed here).

## 4. Market (checked 2026-08-23)

| product | what it ranks on | trend over time? | claim → papers? | notes |
|---|---|---|---|---|
| Hugging Face Daily Papers | community upvotes, ~2–3 % of arXiv | no (daily/weekly lists) | n/a | added a "Trending" list after PWC closed |
| alphaXiv | discussion/engagement | no | n/a | comments + author Q&A |
| Emergent Mind | X/HN/Reddit/GitHub mentions + recency | no | n/a | social-signal ranking, AI summaries |
| Paper Espresso (open source) | HF upvotes, Gemini summaries/labels | yes, over the upvoted 2–3 % | yes — parquet drill-down | closest in spirit; sample is social, labels are LLM-generated |
| AI Papers Academy H1-2026 report | keyword share over 171k papers | yes, static | **no — aggregates only** | the exact liability shape §1 avoids |
| NLLG quarterly arXiv reports | citations + keywords | yes, quarterly PDF | partially (top-40 lists) | academic, not a site |
| Papers with Code | leaderboards | — | — | shut July 2025; data on HF |
| Paperscape / Connected Papers / Litmaps / ResearchRabbit | citation graphs | no | per-paper | discovery, not trends |

The gap: **continuously refreshed, full-coverage (not social-sampled) trend
series over a whole arXiv category, where every number is a reproducible
query with its paper list attached and a public flag path.** Nobody in the
table does all of: parity freshness, full coverage, time series,
drill-down, and flagging. Most do none of the last two.

## 5. Costs

| | |
|---|---|
| Weekly job | 1.7 GB download (skippable when the seed hasn't changed), ~10 min CPU, no LLM |
| Disk | ~200 MB catalog + ~20 MB trends, two generations kept |
| Serving | two more `:ro` SQLite files; trend endpoints are indexed reads |
| Money | $0 recurring |
| Legal posture | CC0 metadata only; abstracts displayed (explicitly permitted, §6b item 5); no full text; flag + exclusion path |

## 6. Decisions for the owner

1. **Scope of the catalog**: cs.CL-any (recommended: 111k rows, what the
   site is about) vs cs.* (772k, ~1.3 GB, broader trends, slower mining).
2. **Default denominator**: share of the month (recommended) vs count.
3. **Flag destination**: GitHub issues in the public repo (recommended —
   public fixes, no backend) vs an email link.
4. **Page placement**: `/trends` sibling page (recommended) vs a mode
   inside the one shell.
5. Whether mined n-grams ship in v1 or only the curated list (mined
   surfaces surprises; curated is fully reviewable — recommended: both,
   labeled).
