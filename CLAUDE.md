# askRAG — agent contract

<!-- Maintainers: this file is a CONTRACT, not documentation. It is owned by the
coordinator session and changes like code (commits, reviewable diffs). Budget:
150 lines hard ceiling. History lives in git, never in this file. -->

Public portfolio project: agentic RAG over 6,460 arXiv CS papers (11.6 GB).
The agent is a side panel that feeds itself (tools, not context-stuffing),
on a hand-built loop, deployed for ≤$22/mo. Currently pre-code: spec is done,
work is broken into GitHub issues.

## Source of truth (read before building anything)

- **The spec**: `docs/superpowers/specs/2026-07-04-agentic-rag-design.md` —
  14 decision records (D1–D14) with revisit triggers, tool contracts (§5),
  threat model (§6), arXiv compliance (§6b/§6c), repo layout (§4c),
  engineering principles (§4d). If code and spec disagree, the spec wins;
  if the spec is wrong, change the spec first (it's a numbered decision).
- **Map**: `docs/architecture.html`. **Look & feel**: `docs/mockup.html`
  (the PDF.js continuous-scroll viewer there is the reference behavior).
- **Work**: issues #9–#39 on nabinpkl/rags, board
  https://github.com/users/nabinpkl/projects/2

## Work protocol

- Pick tasks ONLY from the board's **Ready** column. Blockers are in each
  issue's opening line. When you close an issue, search its number and move
  newly-unblocked issues from Backlog to Ready.
- An issue's **Acceptance checklist is the definition of done** — check items
  off in the issue and record measured numbers (latency, failure rates, cost)
  as issue comments; several close spec §10 assumptions.
- Issues labeled `needs-human` end with a step only @nabinpkl can do — park
  in "In review" and say what's needed.
- Work in-place on `main` unless told otherwise. Never create branches or
  worktrees on your own initiative.

## House rules (spec §4d, condensed)

- No grab-bag files: no `utils.py`, `core.py`, `helpers.py`, `service.py`.
  One responsibility per file, ~400-line soft cap. (Sole exception:
  `frontend/lib/utils.ts` holding shadcn's `cn()`.)
- Tests mirror source names 1:1 (`budgets.py` ↔ `test_budgets.py`).
  Security-relevant behavior (spec §6 table) is NEVER test-after.
- Knowledge lives once: every tunable in `askrag/config.py`; SSE vocabulary
  in `askrag/api/sse_events.py` (frontend `lib/sse.ts` mirrors it under
  test); `frontend/lib/api-types.gen.ts` is generated, never hand-edited.
- Explicit over implicit: the tool registry is a literal dict; no
  metaprogramming, no decorator scans, no dynamic imports.
- Comments state constraints the code can't ("read-only by construction,
  see D4"), never narration.
- Any deviation from a spec decision needs a new/updated decision record in
  the spec — no silent architecture drift.

## Hard constraints (violating these is a security/legal bug)

- **Never serve, proxy, or cache arXiv PDFs or bulk full text from our
  infrastructure** (§6b). PDFs reach users only via their browser fetching
  arxiv.org, always **version-pinned** (`…/pdf/<id>v<N>`).
- **No UI/API path returns full paper text** for default-license papers
  (§6c): quotes ≤50 words, ≤3 per paper per answer, server-enforced.
- Agent tools are **read-only by construction**; `query_metadata` is
  single-statement SELECT-only; sandbox runs `--network none` with ro
  mounts; `drive_ui` accepts enums, never URLs or HTML.
- Retrieved paper text is untrusted (injection surface) — always fenced.
- The verbatim arXiv attribution + takedown link stay in the site footer.

## Commands

- Collector: `just status`, `just diverse`, etc. (see `collector/` after #9;
  currently repo root). Corpus artifacts live under `corpus/` (gitignored).
- Backend (after #10): `uv run pytest`, `just be-lint`, `just ingest`,
  `just eval`. Frontend (after #26): `pnpm build`, `pnpm gen:api`.
  <!-- Update this section as recipes land; wrong commands are worse than none. -->

## Evolving this file (coordinator mandate)

The coordinator session keeps this file lean and true; other agents propose
changes as diffs but do not merge them.

- **Add** when an agent makes the same mistake twice, or a correction recurs
  across sessions — one line, concrete enough to verify by observation.
- **Route by lifetime**: always-relevant → here. Path- or language-specific
  → `.claude/rules/<topic>.md` with `paths:` frontmatter. Sometimes-relevant
  reference or a multi-step workflow → a skill. Must-hold-every-time → a
  hook (then delete the prose version here).
- **Prune** whenever Claude misbehaves and at every milestone close: for each
  line ask "would removing this cause mistakes?" — if no, cut. If agents
  already do it correctly, cut. If it contradicts the spec, fix the spec
  pointer, don't fork content here.
- Command lists and issue/board pointers must match reality — stale pointers
  get fixed in the same commit that changed reality.
