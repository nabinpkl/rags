# SDLC workflow — coordinator / implementor / reviewer

One coordinator session, one persistent implementor agent, one persistent
reviewer agent. Work flows through GitHub PRs; the coordinator is the only
role that merges. Role briefs live in `.claude/briefs/`.

> The generic shape of this loop — roles, green definition, dependency gate,
> idiom-deviation rule, coherence auditor — now lives once in the taste plugin
> (`taste:agent-orchestration`); the tmux scripts and branch hook are installed
> from there by `just harness-install`, not vendored in this repo. This file
> keeps only askRAG's project-specific delivery details.

## Roles

- **Coordinator** (the main session): owns the board, assigns one issue at a
  time to the implementor, relays diffs and findings between the two agents,
  arbitrates disputes (spec is the tiebreaker), merges PRs, closes issues,
  promotes newly unblocked board items, and maintains `DECISIONS.md`,
  `CLAUDE.md`, and the spec.
- **Implementor** (one instance, continued across tasks): implements exactly
  one issue at a time on a branch, self-reviews the diff before handoff,
  opens the PR, judges every review finding (fix, or reject with stated
  reasoning), pushes fix commits. Never merges.
- **Reviewer** (one instance, continued across tasks): read-only. Reviews
  the PR diff fresh each round, files findings with file:line, severity, and
  a concrete failure scenario. Never edits code. Verdict per round:
  `GREEN` or `FINDINGS`.

No parallel implementors, no fresh implementor per task: continuity of
context is the point. If the coordinator session restarts, re-spawn roles
with their briefs; durable context lives in artifacts (PRs, issue comments,
DECISIONS.md, the spec), not in any agent's memory.

## Worker harness (tmux)

Workers run as interactive `claude` CLIs in tiled panes of one `agents` window
in the human's **pre-existing** `rags` tmux session, so both the coordinator and
the human can watch them work (DECISIONS.md 2026-07-06). Three roles:
`implementor`, `reviewer` (per-PR, Sonnet), and `auditor` (Opus, read-only,
slice-boundary coherence — see below). Scripts in `scripts/`:

- `agent-spawn.sh <role> [task-file]` — adds the worker as a **pane in the
  shared `agents` window** (tiled grid, `@role` titled borders), running in its
  **own git worktree** at `.worktrees/<role>` so worker git ops never collide
  with the coordinator (who stays on `main` in the primary repo) or other
  workers. Pinned to a known `--session-id`. Knobs: `AGENT_BASE` (ref the
  worktree is detached at, default `origin/main`; `origin/<pr-branch>` for the
  reviewer), `AGENT_MODEL` (e.g. `opus` for the auditor). **Fails loud if the
  session is absent; never creates it** (the human owns its lifecycle).
- `agent-send.sh <role> <msg>` — deliver a short control message (type, settle,
  submit). Big context (task specs, findings) goes in a file or PR comment;
  send a one-line "read <path> and act", not kilobytes through tmux.
- `agent-feed.sh <role>` — the human's peek: one line per tool call, mutating
  tools flagged, read from the live-appended session jsonl (not TUI-scraped).
- `agent-pane.sh <label> <cmd>` — a worker opens a **visible** split pane for a
  **long** run (ingest, embed, eval, full suite, benchmark), teeing to
  `.claude/run/task-<label>.log`. Short commands stay in the worker's Bash.

Two channels, kept separate: the on-disk jsonl is the coordinator's machine
signal (tool calls + terminal result event); the tmux window + feed is the
human's live view and manual override (attach, Ctrl-C to halt, type to steer).
At a coherent task boundary the coordinator kills and re-spawns the worker
(compaction-by-respawn) and removes its worktree. Workers run same-account, so
this makes limit deaths visible and cheap-to-resume, not impossible;
`ANTHROPIC_API_KEY` on the workers is the unwired escape hatch for true
isolation. Human vigilance is sampling, not a gate: actions that must never
happen are stopped by permission mode and hooks, not by someone watching.

**Coherence checkpoints (the `auditor` role).** Per-PR review — at any model
tier — only sees the diff; it cannot see cross-issue drift. At each vertical
slice / epic boundary, and before any architecturally load-bearing issue, the
coordinator spawns the auditor (Opus) to read the *whole* slice + spec +
`DECISIONS.md` + the previous checkpoint and judge coherence: concept
duplication, cross-layer contract rot, spec divergence, and emergent boundary
gaps (e.g. the two-`read_paper`-calls §6c breach that a single diff never
shows). It writes `docs/checkpoints/<date>-<slice>.md` with a `COHERENT` /
`NEEDS-WORK` verdict; `NEEDS-WORK` items gate the next slice. Load-bearing PRs
(the agent loop, the public API/SSE surface) additionally get an Opus review
pass on top of the standard Sonnet review; routine PRs stay Sonnet.

## The loop (per issue)

1. Coordinator picks the top item from the board's **Ready** column, moves it
   to **In progress**, sends the implementor the issue number plus any
   coordinator notes.
2. Implementor: branch `issue-<n>-<slug>` → implement + tests → self-review
   the whole diff as one system → `gh pr create` (body: what/why, acceptance
   checklist status, verification evidence, risks) → hands back PR number.
3. Coordinator moves the card to **In review**, sends the PR to the reviewer.
4. Reviewer files findings as one PR comment per round (structured, see
   brief), ending with `VERDICT: GREEN` or `VERDICT: FINDINGS`.
5. On FINDINGS: coordinator relays to implementor. Implementor replies to
   each finding on the PR: `FIXED <commit>` or `REJECTED: <reasoning>`,
   pushes fixes. Coordinator sends the new diff back to the reviewer.
6. Repeat. **After 3 FINDINGS rounds the coordinator arbitrates**: each
   unresolved finding is decided against the spec, the decision goes in the
   PR thread, and if it changed anything architectural, in `DECISIONS.md`.
7. On GREEN + the full green definition below: coordinator squash-merges
   (`gh pr merge --squash`), subject `<type>: <summary> (#<issue>)`, closes
   the issue with measured numbers commented, moves the card to **Done**,
   searches the issue number and promotes newly unblocked issues to
   **Ready**.

## Green definition (all required)

- CI green (lint, types, tests).
- Issue acceptance checklist fully checked, measured numbers recorded.
- Anything user-visible: verified on the real surface via Playwright
  (`e2e/demo-flow.spec.ts` once it exists; ad-hoc Playwright before then),
  screenshot or trace attached to the PR. "The code looks right" is not
  verification.
- Reviewer `VERDICT: GREEN` on the final diff.
- No finding left in an unjudged state (every one FIXED or REJECTED with
  reasoning).

## Decisions outside the spec

Any choice the spec doesn't already make (or contradicts) stops the loop:

1. Coordinator logs it in `DECISIONS.md` (dated entry: context, decision,
   alternatives, consequence).
2. The spec gets a new or amended decision record **in the same PR** as the
   code that depends on it. `DECISIONS.md` says which spec section changed;
   "Spec updated: pending" is only acceptable for process-only decisions.
3. Silent drift between code and spec is a bug (CLAUDE.md hard rule).

## Dependency gate

Spec §4b packages are pre-approved. Anything else, before it enters a
lockfile **or a CI workflow file** (GitHub Actions are dependencies: they
run with the repo token):

- **Popular**: meaningful adoption (registry download rank, stars, known
  users) — not a judgment call, cite the number.
- **Actively maintained**: a release within the last 12 months AND
  human-reviewed merges (not only bot commits).
- **Security**: no unresolved critical advisories (`pip-audit` /
  `pnpm audit` + GitHub advisory DB); check for install scripts
  (`preinstall`/`postinstall`) and typosquat-adjacent names; pin the version.
- **CI actions**: pass the same popularity/maintenance/security checks and
  are **pinned to a full commit SHA** with the version as a trailing
  comment (`uses: owner/action@<sha>  # vN`). A mutable tag is not a pin.
  Applies to every action, first-party included — one rule, no judgment
  calls per action.
- Gate evidence carries **measured numbers** (checked on the day, source
  named), never remembered ones.
- Result recorded as a `DECISIONS.md` entry (name, version, numbers checked,
  verdict). The implementor proposes, the coordinator approves the entry
  before the dep lands.

## Idiom defaults

Code is idiomatic for its ecosystem by default; the binding per-path rules
live in `.claude/rules/` (`python-backend.md`, `frontend.md`) and apply to
both implementor and reviewer. When idiomatic is unaffordable or actively
hurts, the implementor deviates and logs a `DECISIONS.md` entry (what, why,
revisit trigger) in the same PR — **no human sign-off needed**; the entry
exists so the deviation can be revisited, not to gate it. The reviewer
treats undocumented non-idiom as a finding (severity by blast radius) and
reviews documented deviations against their stated reasoning.

## GitHub mechanics and constraints

- All three roles act as one GitHub account, so GitHub blocks formal PR
  approval on our own PRs. The reviewer's `VERDICT: GREEN` comment is the
  approval of record; the coordinator's merge is the sign-off.
- Branch per issue, deleted after squash-merge. `main` stays releasable.
- The board README's lane rules still apply; the coordinator owns all card
  moves so lane state has one writer.

## Escalation to the human

Stop and ask @nabinpkl when: an issue is labeled `needs-human` and its human
step is reached; a decision would change a spec hard constraint (§6b/§6c,
budgets, read-only tools); the 3-round arbitration would overrule a security
finding; or a dependency fails the gate but seems necessary (the alternative
is scope change).
