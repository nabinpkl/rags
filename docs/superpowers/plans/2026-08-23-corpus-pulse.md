# Corpus pulse — a dashboard that moves without being asked

Status: **proposal**, 2026-08-23. Not an issue yet; becomes issues once the
owner picks a variant (§5).

## 0. The problem, honestly stated

The first screen is a table of 200 papers sorted by year, and an agent panel
that waits. Nothing on it changes between visits. The user's ask: freshness,
"what's happening", a dashboard that is proactive rather than reactive.

Three facts bound what "fresh" can mean here (all measured 2026-08-23):

| Fact | Source | Consequence |
|---|---|---|
| Prod serves **200** papers, not 6,460 — D16 scopes the API to chunked papers; only 200 are chunked (#15 open) | `facets.py:37`, `/api/facets` → `total: 200` | Any dashboard is over 200 papers until #15 lands. **#15 is the gate.** |
| The corpus is a **frozen snapshot** (D12: `2026-07`, newest paper 2026-06-25). A daily cron on the VPS is explicitly *rejected* in D12 | spec D12 | "New papers" at serve time is impossible by design; freshness = refresh cadence + what we compute *at* refresh |
| The live agent budget is **$0.50/day global** (D11) | `config.py:189` | A proactive agent cannot be an online loop. Proactive = **offline work shown at zero marginal cost** |

Plus two shape facts that are assets, not constraints:

- The corpus has a time axis worth showing: ~240 papers/yr 2007–2025 (the
  diverse sample) and a 1,873-paper spike Apr–Jun 2026 (1,397 in June alone).
  Day-precision `published` exists in `corpus.db` but reaches the API only on
  the detail route; list sorting is by integer `year`.
- `traces.db` already records every agent run (question, answer, tool calls,
  cost) and has a `showcase` flag that D11's replay mode reads — and **nothing
  ever sets it** (`loop.py:327` hardcodes `False`), so replay mode 503s today.
  A digest job that records showcase runs fixes a latent D11 gap for free.

Things ruled out by data: *trending by citations* (the frozen citation file
covers 3,063/6,460 papers with 125 intra-corpus edges); *live arXiv polling
from the browser or API* (§6b pacing + D12).

## 1. Principle

> The agent already did the work — the page shows it.

Freshness comes from two clocks, both offline:

1. **Refresh clock** (monthly, operator-run, D12-compatible): `update` pulls the
   OAI delta, ingest chunks/embeds only new papers, a **digest job** runs the
   agent over a fixed prompt set and records the runs as showcase traces,
   then `deploy-reseed`. The snapshot date advances; the dashboard's "newest"
   set and briefings change.
2. **Day clock** (serve time, no LLM): spend meter, "N days since snapshot",
   which briefing is featured today (rotation keyed on the date), and the
   per-day slice of the newest papers. Cheap SQL over immutable data — compute
   once per process, not per request.

Nothing in this plan runs an LLM in response to a page load.

## 2. What the dashboard shows

Lives as the **default state of the explorer region** (no `q`, no filters,
no paper) — a "pulse" band above the table that collapses the moment a
filter or search is applied. Not a new route (§4c: one shell), not a new
region mode in `viewer-store`, and the explorer stays the primary surface
(§2). On a phone it is the first screen.

```
┌ Corpus pulse ─────────────────────── snapshot 2026-07 · 59 days old ┐
│                                                                      │
│  NEWEST IN THE CORPUS          │  THE AGENT'S BRIEFING (AI-generated)│
│  Jun 25  Multilingual Reasoning…│  "June's cs.CL papers cluster on   │
│  Jun 25  Paved with True Intents│   three things: …" — 6 citations   │
│  Jun 24  …                      │  [▶ replay this run]  $0.018 · 7 s  │
│  + 1,394 more from June   →     │  ◦ ◦ ● ◦ ◦   (rotates daily)        │
│                                                                      │
│  24 MONTHS  ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂▄█  │  MOVERS this quarter vs trailing │
│  cs.CL 2,719 · cs.LG 467 · …       │  cs.CL ▲ · cs.CV ▲ · cs.IT ▼     │
│                                                                      │
│  LIVE  $0.13 of $0.50 spent today · 4 questions answered · replay on │
└──────────────────────────────────────────────────────────────────────┘
  ↓ the existing table
```

Cards, each backed by a field of one `GET /api/pulse` response:

| Card | Data | Interaction |
|---|---|---|
| **Newest** | top N by `published` desc (day precision) + count for the newest month | row → open paper; footer → `set_filters(year_min=…)` + `sort=newest` in the table |
| **Briefing** | the featured digest run: `answer_text` (already §6c-capped), citations, cost, latency; index into the digest pool by `day_of_year % n` | citation → open paper at page; **replay** → plays the recorded trace through the agent panel's timeline (D11 path, `replay.py`) — the agent visibly "does" something on first load without spending a cent |
| **24 months** | per-month counts, last 24 months (a sparkline; the year histogram already exists in the facet rail, this is the month version) | bar → filter to that month (needs `published` range filters or month→year fallback) |
| **Movers** | category counts in the newest quarter vs the trailing 12 months, as a ratio | chip → `set_filters(category)` |
| **Live** | `spend_today_usd`, `cap_usd`, `runs_today`, `mode: live\|replay` | none; this is the D11 architecture made visible ("the architecture is the demo") |

Agent panel first-run state gets the same briefing as a starter: "While you
were away the agent read June's papers — ▶ replay, or ask your own." The
three `SUGGESTED_QUESTIONS` stay.

Labeling: every briefing carries "AI-generated · cited · recorded <date>"
(§6c row 3). Quotes inside are already capped server-side at answer assembly.

## 3. Work, in order

### Phase 0 — unblock: full-corpus ingest (#15, needs-human)

Gate for everything. Measured cost: the one recorded embed run did 6,694
chunks in 31 min on a Mac GPU (`embed_run_local_fp16_20260705.log`); the
corpus averages 40 chunks/paper → ~260k chunks ≈ **20 GPU-hours**, or days
on this 4-core host. Options the owner must pick from: run it on the Mac
overnight in batches (the embedder resumes — `already_embedded` is tracked);
or flip `embedding_backend=voyage` for the one-time bulk and keep local for
queries (D5 allows either; same model family must hold — check before
choosing). Deliverable is the existing #15 checklist.

### Phase 1 — backend: day-precision recency + `/api/pulse`

- `PaperListItem.published` (it is already on the detail model; list rows
  only carry `year`). Regenerate `api-types.gen.ts`.
- `sort=newest` (`published DESC, arxiv_id DESC`), keyset cursor on
  `(published, arxiv_id)`. Four rows have `published=''` — they sort last
  by construction (`ORDER BY published = '' , published DESC`).
- `GET /api/pulse` → `PulseResponse { snapshot, built_at, newest: [...],
  months: [{month, count}], movers: [{category, recent, trailing}],
  briefings: [{run_id, question, answer_text, citations, cost_usd,
  latency_ms, recorded_at}], featured_index, live: {spend_today_usd,
  cap_usd, runs_today, mode} }`.
  Corpus parts computed once per process (the snapshot is immutable — cache
  with `functools.lru_cache` keyed on `meta.built_at`); `live` is one
  `traces.db` read per request (it is the same query the budget gate already
  does). No LLM.
- `askrag/api/routes_pulse.py` + `askrag/pulse.py` (the SQL) + tests
  mirroring names. `query_metadata` gets nothing new — the agent does not
  need this endpoint.

### Phase 2 — offline digest job: `just digest`

- `askrag/digest/prompts.py`: a literal list of ~6 standing questions,
  parameterised on the snapshot's newest month/quarter ("What are the three
  most common themes in cs.CL papers from {newest_month}?", "Which
  {newest_quarter} papers are from top-rigor venues and what do they
  share?", one per top-3 category, one cross-category "what's unusual").
- `askrag/digest/run.py`: runs the existing agent loop (`askrag.cli`
  one-shot path) per prompt against prod config, **records with
  `showcase=1`**, tagged `digest=<snapshot>`. Cost: ~6 runs × ~$0.02 ≈
  $0.12 per refresh, charged outside the daily cap (it is operator spend,
  not visitor spend — the budget gate must be bypassed by the job, not
  raised). This also populates D11's showcase pool, so replay mode stops
  returning 503 — a latent bug this closes.
- Old digests are kept, newest snapshot's are preferred; `featured_index`
  rotates across the current pool.
- Records a DECISIONS.md entry: showcase traces are minted by the digest
  job, not hand-picked (D11 amendment).

### Phase 3 — frontend: the pulse band

- `components/explorer/pulse-band.tsx` (composition), one file per card:
  `pulse-newest.tsx`, `pulse-briefing.tsx`, `pulse-months.tsx`,
  `pulse-movers.tsx`, `pulse-live.tsx`; `hooks/use-pulse.ts`
  (`staleTime: 5 min`, `refetchInterval: 60 s` for the live card only —
  split into two queries so the corpus half never refetches).
- Band renders only when `viewer-store` has no `q`/`category`/`yearFrom`/
  `yearTo`; `@container` inside, cards reflow 2→1 columns by region width
  (per `.claude/rules/frontend.md`).
- Replay button drives the existing agent-session replay path; the panel
  opens (drawer on phone) and plays the timeline.
- "Newest" rows reuse the table's row component so click/keyboard semantics
  are identical.
- Tests: `pulse-band.test.tsx` (hidden under any filter; shown at rest),
  `pulse-briefing.test.tsx` (AI-generated label always present; replay never
  calls `ask`), `use-pulse.test.ts` (live query polls, corpus query does not).

### Phase 4 — cadence: `just refresh` and the snapshot banner

- Root recipe `refresh`: `update` → ingest delta (only un-chunked papers —
  already the embedder's behaviour) → `digest` → `deploy-reseed`. One
  command, documented in `deploy/README.md` "Refreshing the corpus".
- The footer's `corpus 2026-07` gains "· N days old" from `/api/pulse`.
- D12 amendment: cadence "monthly, operator-run" replaces "quarterly";
  still no serving-side ingest, still rejected: cron on the VPS. Revisit
  trigger unchanged.

## 4. What it costs

| Item | Cost |
|---|---|
| Phase 0 (one-time) | 20 GPU-hours on the Mac, or a Voyage bulk run (free tier) |
| Digest per refresh | ~$0.12 (6 Haiku runs); ~$1.50/yr at monthly cadence |
| Serve-time | zero LLM; one SQLite read per `/api/pulse` for the live card |
| Monthly refresh, operator time | ~30–60 min incl. the delta embed (June-sized months are ~1,400 papers ≈ 56k chunks ≈ 4 GPU-hours — the cadence cost is dominated by embedding, flag if a month is large) |

Stays inside the ≤$22/mo ceiling with no new line item.

## 5. Decisions the owner makes (the plan stops here without them)

1. **Phase 0 route**: Mac GPU in batches vs Voyage bulk embed. (Blocks all.)
2. **Dashboard placement**: default state of the explorer (recommended,
   above) vs a third region mode (`?view=pulse`). The former needs no spec
   change beyond §2 wording; the latter touches §4c.
3. **Cadence**: monthly operator-run (recommended) vs quarterly as D12
   stands today vs a host `systemd` timer (a D12 amendment with a real
   revisit trigger — "if a timer run ever fails silently").
4. **Briefing pool size and prompt set** — 6 is a guess; more prompts is
   more rotation and more operator spend per refresh.

## 6. Not in this plan

- Showing visitors' own questions ("what people are asking") — user-authored
  text is an injection and moderation surface the spec doesn't cover; only
  digest runs (operator-authored prompts) appear on the page.
- "Similar papers" from the chunk embeddings — plausible later, not freshness.
- Any serve-time LLM call, any browser-side arXiv fetch, any full-text
  display (§6b/§6c unchanged).
