# Landing page you don't type into, research surface behind it

Status: **proposal**, 2026-08-24. Supersedes the framing in
`2026-08-23-corpus-pulse.md` §5 (variant choice) and folds in
`2026-08-23-trend-index.md` (transparency rules) and
`2026-08-23-agentic-trend.md` (tools). Not issues yet.

## 0. The shape

Two surfaces, one product:

1. **Landing page** — freshness + citations, rendered from deterministic rules.
   No input box in the critical path. A visitor understands what the site is
   from the first screen without typing a character.
2. **Research surface** — RAG/agent over paper full text, entered *from a claim
   on the landing page*, never from a blank prompt.

The landing page is the demo. The agent is what the demo lets you do next.

## 1. What is measured and on disk (2026-08-24)

| Fact | Value | Source |
|---|---|---|
| Google mirror, whole | 2,725,557 papers / 5.86 TiB | full object listing, `scratchpad/mirror_sizes.tsv` |
| whole cs, all history | 804,098 papers / 2.60 TiB | mirror × Kaggle join |
| AI core (AI/LG/CL/CV/NE), any position | 592,401 / 2.30 TiB | same |
| steady-state cs | ~13,800 papers/mo, 65 GiB/mo of PDF | per-month join, 2501–2607 |
| PDF vs its own text | 4.7 MB vs 68 KB — **70×** | `corpus/text` mean |
| papers we hold text for | 18,466 (Jul 2026 + Aug 1–14) | `corpus/text` |
| of those, carrying ≥1 arXiv-id reference | 15,543 (84.2%) | `scratchpad/edges.tsv` |
| citation edges | 158,224 → 62,195 distinct cited papers | same |
| cited papers **outside** our window | 98.3%, of which 97.4% resolve in the Kaggle catalog | same |
| **papers actually chunked and embedded** | **200** (7,974 chunks, 39.9/paper, 560 tok/chunk) | `corpus.db` |
| embed throughput, Mac GPU (nomic fp16) | 3.6–4.2 chunks/s | `embed_run_local_fp16_20260705.log` |
| embed throughput, VPS CPU | 0.66 chunks/s | `embed_run_20260705.log` |

## 2. The blocker: the page covers 18,466 papers, the agent covers 200

D16 scopes the API to chunked papers. 200 are chunked. So the page can honestly
say "Qwen3 is cited 1,137 times by papers submitted this month" and the agent
behind it cannot retrieve Qwen3, or any of the 1,137 citers.

A landing page whose every link dead-ends in the agent is worse than no landing
page: it advertises a capability and then withholds it. Closing the gap by
indexing everything is not free:

| index scope | papers | chunks | Mac GPU | VPS CPU |
|---|---|---|---|---|
| everything we have text for | 18,466 | 737k | 57 h | 13 days |
| every paper the page can reach (top-200 targets + all their citers) | 8,649 | 345k | 27 h | 6 days |
| **the top-50 story, fully answerable** (50 targets + 8 example citers each) | **272** | **11k** | **51 min** | **4.6 h** |

## 3. Resolution: the page defines the index frontier

Invert the dependency. Today: index a corpus, then build a page over whatever
got indexed. Instead: **the page's claims are the index manifest.**

Every card on the landing page is a rule with a bounded result set. Chunk and
embed exactly the papers those result sets name — the cited papers a card
ranks, plus a capped sample of the citers behind each. Nothing else. The
frontier is 272 papers for the top-50 story, and grows only when a card is
added or its cap is raised.

Consequences:

- Every link on the page is answerable **by construction**, which is a
  stronger property than "most of the corpus is indexed".
- The cited side needs 50–200 PDF fetches (papers from 2014–2026 that are not
  in our window) — ~1 GB, minutes on the mirror.
- The frontier is recomputed when the page is regenerated, so it tracks the
  story rather than accumulating.
- It fits the $0.50/day cap (D11) because indexing is offline and the serve-time
  cost is unchanged.

**Storage model change**: retain text + citation edges, treat the PDF as a
transient (fetch → extract → delete). That takes the ceiling from ~5 months of
whole-cs PDFs to the entire cs archive in text form (~52 GiB), and frees the
77 GiB we currently hold for July–August. §6b is unaffected: we still never
serve or proxy a PDF, and §6c quote caps still bind the API.

## 4. Landing page composition

Every card: a headline number, the rule that produced it in plain text, a
drill-down to the papers it counted, and a flag link. No card states a
conclusion the rule does not compute. Carried over from
`2026-08-23-trend-index.md`: *a trend is a saved query, and the page shows the
query's result set, not a conclusion about it.*

1. **What this month builds on** (top story). The weekly citation series over
   the window, with the cited papers ranked. Real numbers: Qwen3 1,137 · Llama 3
   774 · DeepSeekMath/GRPO 746 · Qwen3-VL 587 · GPT-4 532 · PPO 530 (2017) ·
   DeepSeek-R1 507 · Adam 317 (2014).
2. **Reach back**. Share of edges by cited year — 6.5% pre-2020, 12.0% 2023,
   18.8% 2024, 31.1% 2025, 18.2% 2026. This is the card that makes the corpus
   legible: half of what this month cites predates 2025.
3. **Volume**. Papers per submission day over the window, cs-primary, against
   the trailing-6-month mean.
4. **Category movers**. Primary-category share this month vs the trailing
   baseline, ratio, drill-down.
5. **Coverage, stated plainly**. 18,466 papers with text; 84.2% yielded an
   arXiv-id reference; window is Jul 1 – Aug 14 2026; catalog snapshot v300.

Dropped: the n-gram rising/falling terms card. Two runs showed it surfaces
prose, not topics; title-gating cut the noise but not the semantics problem.
Citations carry the same signal with a paper behind every number.

## 5. The ask surface

Entry is always a claim, never an empty box. From "Qwen3 — 1,137 citing papers"
the visitor gets scoped openers computed from the edge set, e.g. *"What do these
1,137 papers use Qwen3 for?"* / *"Which of them report replacing it?"* The
agent's retrieval is restricted to that claim's paper set, which is why the
frontier in §3 is sufficient.

This is also the honest answer to "why an agent at all": the page tells you
*that* 1,137 papers cite Qwen3; only reading them tells you *what for*, and
that is a retrieval job over full text with §6c quote caps.

## 6. Cadence

Monthly, manual, no cron (D12 rejected a VPS cron and this does not revive it):
pull the month's PDFs → extract text → drop PDFs → recompute edges and card
rules → derive the frontier → chunk and embed the frontier → regenerate the
page. The expensive step is the embed, and §3 sizes it at under an hour on the
Mac for the top-50 story.

## 7. Spec deltas required

- **D16** (API scoped to chunked papers) — unchanged as a rule, but the *reason*
  the scope is acceptable changes: the indexed set is now derived from the
  page's manifest rather than being an arbitrary prefix of the corpus. Needs a
  revisit-trigger amendment.
- **D12** (frozen snapshot) — the snapshot becomes "the papers this month's page
  points at", refreshed on the §6 cadence. Still no serve-time freshness.
- **New decision needed**: PDFs are transient, text and edges are the retained
  artifacts. This touches §6b's wording (which prohibits serving/caching PDFs
  and bulk full text externally, not internal text extraction) — the amendment
  should make the internal/external distinction explicit rather than leave it
  inferred.

## 8. Open

- 15.8% of papers yield no arXiv-id reference. State it on the page; do not
  silently imply full coverage.
- One window supports "what this cohort builds on", not "rising". A rising claim
  needs ≥6 monthly windows of citing papers — transfer-bound (~390 GiB), not
  disk-bound (~6 GiB retained).
- `metadata-v5/internal-citations.json` on the mirror is frozen at 2020-08-19;
  usable as a pre-2020 backbone, useless for the recent side.
- The deployed agent is currently non-functional (OpenRouter key invalid,
  `ANTHROPIC_API_KEY` empty). §5 cannot be demonstrated until that is fixed.

## 9. What "fresh" means (proposal, under discussion 2026-08-24)

Freshness is a **vantage point, not a corpus boundary**. The 2-month window is a
full-text limit, not a coverage limit: the Kaggle catalog gives title+abstract
for all 3.14M arXiv papers at zero download cost, and an abstract-level index
over all of cs history is affordable where full text is not.

| index tier | unit | chunks | tokens | index | embed (Mac / VPS) |
|---|---|---|---|---|---|
| breadth: every cs paper ever | 1 abstract | 804,098 | 315 M | 5.5 GB | 56 h / 338 h |
| breadth: AI core only | 1 abstract | 592,401 | 238 M | 4.0 GB | 41 h / 249 h |
| depth: full text of what we hold | ~40/paper | 0.70 M | 0.39 B | 4.7 GB | 48 h / 293 h |
| (rejected) full text, whole cs | ~40/paper | 25.9 M | 14.5 B | 176 GB | 75 d / 1.2 y |

Three meanings of "fresh", separated because they cost differently and only one
is differentiated:

1. **Fresh cohort** — which papers count as "now" (Jul 1 – Aug 14 2026 today). A
   parameter, not a feature.
2. **Fresh answer** — how current the reply is; bounded by the window's end.
   Every competitor claims this; it is table stakes.
3. **Fresh consensus** — what the newest cohort collectively points at.
   Citation-derived, and it inherently reaches back through all history (half of
   our edges land pre-2025). **This is the product.**

So the landing page's proposition is not "here are new papers" but *"here is what
the newest work has decided matters"*.

### Question inventory

| question | needs | status |
|---|---|---|
| What is the newest cs built on? | recent full text + catalog | works today |
| Has anyone already done X? | breadth tier | 56 h of embedding |
| Is anyone working on X right now? | breadth tier + recency ranking | same |
| What do they actually report about X? | depth tier | works for the window |
| Who should I read first on X? | breadth + edges | partial |
| Is X rising or fading? | ≥6 monthly windows | **cut from v1** |

"Rising/fading" is cut: one window cannot support it, and it is the claim a
reader is least able to check.

### Consequence for D16

The indexed set becomes two-tier, and the tiers have different honesty
properties: a paper matched at abstract level **cannot be quoted**, because we
do not hold its text. The UI and the tool contracts must distinguish "found" from
"readable" rather than blur them, or the demo implies depth it does not have.
D16 currently assumes a single indexed set and needs amending before the breadth
tier lands.
