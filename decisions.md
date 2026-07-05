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
