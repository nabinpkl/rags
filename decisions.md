# Decisions log

Decisions made outside (or after) the design spec. Newest first. Every entry
that changes architecture must name the spec section updated in the same PR;
"Spec updated: no" is only valid for process-only decisions.

Format:

```
## YYYY-MM-DD — <one-line decision>
Context / Decision / Alternatives rejected / Consequence
Spec updated: <section or "no (process-only)">
```

---

## 2026-07-05 — Live agent LLM: OpenRouter-routed model via env (owner directive)

**Context:** owner provisioned `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
(currently a DeepSeek "flash"-class reasoning model) in `backend/.env`,
replacing D3's Haiku-on-Anthropic-API plan for the live agent.
**Decision:** the live agent model is whatever `OPENROUTER_MODEL` names,
called through OpenRouter's OpenAI-compatible API. Known quirk to build
for (owner-reported, verify against provider docs when #22/#23 land):
reasoning/thinking-token models on OpenRouter require the reasoning blocks
from prior assistant turns to be passed BACK in subsequent requests during
tool-use loops, or tool calling degrades/fails. The hand-built loop (D2)
must persist and round-trip reasoning content per turn.
**Alternatives rejected:** staying on Haiku/Anthropic (owner chose
otherwise; revisit trigger unchanged — model swap is a config change).
**Consequence:** loop.py (#22/#23) is built provider-agnostic against the
OpenAI-compatible schema with reasoning round-trip support; D2/D3 spec
amendment lands in the same PR as that code. Cost model (§7) re-checked
then (DeepSeek pricing differs from Haiku).
Spec updated: pending — D2/D3 amended in the agent-loop PR (#22/#23).


## 2026-07-05 — Frontend scaffold: ESLint pinned to 9; CI gains pnpm/node actions (#26)

**Context:** scaffolding `frontend/` (Next 16 App Router, static export, React
19, Tailwind v4, TypeScript 6 — all §4b pre-approved and latest stable). Two
choices diverge from "just take latest" and need recording.
**Decision:** (1) **ESLint pinned to 9.x, not the latest 10.** ESLint 10.6
breaks an internal API (`scopeManager.addGlobals`) that eslint-config-next 16's
bundled typescript-eslint parser calls, so lint crashes under ESLint 10.
eslint-config-next 16's peer is `eslint >=9`; 9.x is its supported line and
Next 16's documented pairing. Latest-stable of the *compatible* line, not the
newest release. (2) **CI gains two SHA-pinned actions** for the frontend gate:
`pnpm/action-setup@b906aff` (v4, pnpm's own official action) and
`actions/setup-node@49933ea` (v4, first-party GitHub — grandfathered like
actions/checkout per the CI-actions gate). Both run `frontend-check`'s
lint/typecheck/test/typegen-drift in CI.
**Alternatives rejected:** ESLint 10 + overrides/patches (fighting a
bleeding-edge major the plugin ecosystem hasn't caught up to — churn for no
benefit); no CI frontend steps (frontend-check would silently pass without
Node/pnpm present).
**Revisit trigger:** bump ESLint to 10 once eslint-config-next declares
`eslint >=10` support and lint runs clean. `sharp`/`unrs-resolver` native
builds stay disabled (pnpm-workspace.yaml allowBuilds:false) — revisit only if
static export ever needs image optimization.
Spec updated: no (all packages are §4b pre-approved; this records version pins
+ CI-action gate records, not a stack change).

---

## 2026-07-05 — Budget gate is sequentially correct; concurrent overshoot accepted-and-bounded (#21)

**Context:** `budgets.check(session, ip)` is a pre-flight gate — it reads
current spend/counts from traces.py and returns Allow/Deny/Replay *before* a
turn runs. Real cost is known only after the LLM call and written by
`record_run()` afterward, so there is a check-then-record window. D11 does not
specify a concurrency model, and no request-serialization layer exists yet
(that lands with #23 loop / #30 chat route).
**Decision:** enforce SEQUENTIAL correctness now — the gate never Allows once
spend is at/over a cap, so no *sequence* of requests overshoots by more than
one request's cost. Accept the concurrent overshoot as bounded by
`(in-flight request count) × (per-message cost cap)` on top of the $0.50/day
global cap. This preserves D11's ~$15/mo ceiling intent, especially behind
Cloudflare rate-limiting; per-request cost is itself capped by the per-message
token budget, so the bound is small.
**Alternatives rejected:** pre-flight reservation (option 2) — cost is unknown
pre-flight, so it must estimate worst case, pessimistically denying legit
requests near the cap, and adds a reservation-reconciliation path for crashed
requests — speculative complexity for serving layers not yet designed.
App-level locking (option 3) — belongs in whatever runs the request (#23/#30),
not in this pure read-only gate.
**Revisit trigger:** tighten at #23 (loop) / #30 (chat route) with a
reserve-or-serialize step IF real abuse overshoots meaningfully. Money
comparisons use float (matches traces.db `cost_usd REAL` and D3 pricing
floats); sub-cent float drift is negligible against a $0.50 cap.
Spec updated: D11 (appended one sentence on the accepted-and-bounded
concurrent overshoot).

---

## 2026-07-05 — Chunk count is eval-gated, not a target; strict per-section packing ships (#12)

**Context:** strict-D7 chunking (each section packed into ~1k-token windows,
never crossing a section boundary) measured ~7,974 chunks over a real
200-paper extraction set — ~258k projected full-corpus, roughly 2x issue
#12's non-binding 80–120k estimate. 24% of chunks are <200 tokens (short
sections each become a chunk, plus a small tail window per section). One
paper produced 819 chunks — verified genuine (398-page monograph, 16 clean
headings), not a heading over-match.
**Decision:** chunk COUNT is not a spec target; it is eval-gated — D7's
revisit trigger is eval recall@k (D7/D14), not a count. Ship strict
per-section packing as-is. Add `chunk_min_tokens` (default 0 = disabled) to
config.py as the #19 eval-sweep knob; do not change chunking behavior now.
**Alternatives rejected:** tail-merge of sub-threshold chunks (opt 2) —
unmeasured recall risk: a short precise section (a key definition, a dataset
name) is exactly what hybrid retrieval should surface cleanly, and diluting
it into a neighbor could hurt recall; premature before #19 measures it.
Coalescing small adjacent sections (opt 3) — changes D7's "never cross
section boundaries" semantics without eval evidence.
**Consequence:** ~2x baseline chunk count accepted for the demo (embed cost
delta ~$1.5 one-time, <2 GB vectors — no budget concern); revisit at #19.
Spec updated: D7 (appended: count is eval-gated not count-targeted;
`chunk_min_tokens` merge knob exists disabled by default; revisit = #19).

---

## 2026-07-05 — Dependency gate covers CI actions; SHA pins mandatory

**Context:** reviewer questions on PR #45 — the gate said "before it enters
a lockfile", which GitHub Actions never do; the workflow tag-pinned
everything (`@v3`/`@v4`/`@v6`, mutable); and one PR cited a remembered
star count ("~1k") that measured 153.
**Decision:** (1) CI actions ARE dependencies (they run with the repo
token) and pass the same gate; (2) every action is pinned to a full commit
SHA with the version as a trailing comment — one rule including
first-party; (3) gate evidence carries measured, dated numbers.
**Gate record — extractions/setup-just (v3):** 153 GitHub stars (measured
2026-07-05), the installer casey/just's own README recommends, last push
2026-06-24, no install-script surface, no known advisories. PASS.
`taiki-e/install-action` considered (broader, heavier); apt install
rejected (~10x slower). actions/checkout v4 and astral-sh/setup-uv v6
grandfathered as gate-PASS (first-party GitHub / Astral, both already in
use since #10) — re-pinned to SHAs like everything else.
**Alternatives rejected:** SHA-pin third-party only (per-action judgment
calls; one rule is auditable); Dependabot-managed tags (mutable window
remains between releases).
**Consequence:** workflow files show SHAs; bumping an action version is a
deliberate diff. sdlc.md dependency gate amended in this PR.
Spec updated: no (process-only).

---

## 2026-07-05 — ty replaces pyright; tiered `just check` recipes (owner directive)

**Context:** the toolchain was uv + ruff + pyright; checks were scattered
(`be-test`, `be-lint`, CI steps hand-listed).
**Decision:** ty (Astral) is the backend type checker — one vendor for
env/lint/format/types, one speed profile. Check recipes are tiered:
`just backend-check` (ruff, format, ty, fast tests), `just frontend-check`
(pnpm lint + ts checks; graceful skip until #26), `just check` (both) —
and CI runs `just check`, so the local gate and the CI gate cannot drift.
Tracked as issue #44.
**Alternatives rejected:** keeping pyright (second vendor, slower, config
duplication); change-detection inside `just check` (git-diff-driven recipe
selection is cleverness the two side-specific recipes already cover).
**Consequence:** ty is newer than pyright — if it misses real type errors
pyright catches, or false-positives block work, that is the revisit
trigger (swap back is a two-line change since the gate is one recipe).
Spec updated: §4b table, §4c tree.


## 2026-07-05 — Idiomatic-by-default with autonomous deviation logging (owner directive)

**Context:** the review checklist covered hard constraints, correctness,
contract drift, and tests, but had no idiom dimension (Python, FastAPI,
React, state management, state machines).
**Decision:** binding per-path idiom rules live in `.claude/rules/`
(`python-backend.md`, `frontend.md`); implementor and reviewer briefs and
`docs/sdlc.md` wire to them. When idiomatic is unaffordable or hurts, the
implementor deviates and logs a decisions.md entry (what, why, revisit
trigger) in the same PR — explicitly WITHOUT human sign-off; entries exist
for later revisiting, not gating.
**Alternatives rejected:** per-PR human approval of deviations (defeats the
autonomous loop); baking idiom into CLAUDE.md prose (bloats the always-on
contract; path-scoped rules load only where relevant).
**Consequence:** reviewer gains a priority-5 idiom dimension, severity by
blast radius; undocumented non-idiom is a finding, documented deviations
are judged against their own reasoning.
Spec updated: no (process-only).


## 2026-07-05 — Ops telemetry: OpenTelemetry + JSON logs from the start (owner directive)

**Context:** running agents were invisible; owner wants telemetry of every
kind available from day one, not bolted on when the demo is live.
**Decision:** OpenTelemetry initialized at every entrypoint from the start;
JSON-lines stdout is the default exporter, OTLP env-gated off;
`askrag/telemetry.py` is the single setup point; ops telemetry stays
separate from product traces.db. Tracked as issue #43.
**Alternatives rejected:** paid APM (cost cap, data leaves the box); plain
logging (no structure or trace correlation); reusing traces.db for ops
(product vs ops conflation).
**Consequence:** four pinned opentelemetry packages enter §4b pre-approved;
later issues attach spans to the documented naming convention instead of
inventing their own logging.
Spec updated: D15 (new), §4b table, §4c tree.


## 2026-07-04 — PR-loop SDLC adopted: coordinator / implementor / reviewer

**Context:** execution of the spec begins; agents need a repeatable flow.
**Decision:** one persistent implementor and one persistent reviewer agent,
coordinated by the main session; branch-per-issue PRs via `gh`; reviewer
findings judged (fix/reject) by the implementor; 3-round cap then
coordinator arbitration; coordinator is the only merger; Playwright
verification for user-visible work; dependency gate (popular + actively
maintained + advisory-clean) with entries logged here. Full protocol:
`docs/sdlc.md`; role briefs: `.claude/briefs/`.
**Alternatives rejected:** fresh implementor per task (loses accumulated
context); parallel implementors (merge conflicts + divergent conventions at
this project size).
**Consequence:** work is sequential by design; throughput trades for
context continuity. GitHub cannot record formal self-approvals, so the
reviewer's `VERDICT: GREEN` comment is the approval of record.
Spec updated: no (process-only).
