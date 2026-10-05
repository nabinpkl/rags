# askRAG — agent contract

<!-- Maintainers: this file is a CONTRACT, not documentation. It is owned by the
coordinator session and changes like code (commits, reviewable diffs). Budget:
150 lines hard ceiling. History lives in git, never in this file. -->

Public portfolio project: agentic RAG over a sample of arXiv CS (65,503
catalog rows, 29,027 with text, 811 indexed; densest in Jul-Aug 2026).
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
  (the PDF.js continuous-scroll viewer there is the reference behavior) and
  `docs/landing-mockup.html` (the Citations page's original mockup; the live
  page has since cut its copy, so it is layout reference only).
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
- **Delivery flow is the PR loop in `docs/sdlc.md`**: coordinator assigns,
  one persistent implementor builds on `issue-<n>-<slug>` branches, one
  persistent reviewer files verdicts, coordinator merges. Role briefs:
  `.claude/briefs/`. Only the coordinator merges or moves board cards.
- **Commit each arc without being asked.** An arc is one coherent decision
  landed with its tests and doc fallout; when it is complete and `just check`
  is green, commit it. Do not wait for permission and do not let arcs pile up
  in a dirty worktree. Pushing is still asked for explicitly.
- **A job that may run past 2 hours runs detached, never as a harness
  background task** (those are killed at 2 h): `setsid nohup <cmd> >>
  corpus/<job>_<date>.log 2>&1 < /dev/null & disown`, so it outlives the
  session. Watch it by PID (`kill -0 <pid>`), not `pgrep -f`, which matches
  the watcher's own command line.
- Decisions the spec doesn't cover stop the work: log in `DECISIONS.md`,
  amend the spec in the same PR (see sdlc.md).
- New dependencies pass the gate in `docs/sdlc.md` (popular, actively
  maintained, advisory-clean, logged) — spec §4b packages are pre-approved.

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
- Idiomatic by default: per-path language/framework rules in
  `.claude/rules/`; deviating needs a `DECISIONS.md` entry (why + revisit
  trigger), no human sign-off.
- Any deviation from a spec decision needs a new/updated decision record in
  the spec — no silent architecture drift.

## Hard constraints (violating these is a security/legal bug)

- **Never touch export.arxiv.org from any code path** (D18): no OAI
  harvests, no arXiv PDF scraping, no version-backfill queries. Ingest reads
  only the Kaggle snapshot + the GCS mirror; versions backfill from the seed.
- **Never serve, proxy, or cache arXiv PDFs or bulk full text from our
  infrastructure** (§6b). PDFs reach users only via their browser fetching
  arxiv.org, always **version-pinned** (`…/pdf/<id>v<N>`).
- **Nothing fans out to arxiv.org — the frontend included.** One reader
  opening one paper is one request; a list, grid, hover-prefetch, poll, or
  retry loop that touches arxiv.org is a scraper from arXiv's side, whoever
  wrote it. A React effect with a wrong dep array turns thirty visible cards
  into thirty requests per render, so treat any arxiv.org fetch outside the
  viewer's single open paper as a bug to remove, not to rate-limit. Card
  images are rendered from the PDFs we already hold (D19), never fetched or
  screenshotted from arxiv.org at view time.
- **No UI/API path returns full paper text** for default-license papers
  (§6c): quotes ≤50 words, ≤3 per paper per answer, server-enforced.
- Agent tools are **read-only by construction**; `query_metadata` accepts
  only enum'd metadata ops (no model-authored SQL); sandbox runs
  `--network none` with ro mounts; `drive_ui` accepts enums, never URLs or
  HTML.
- Retrieved paper text is untrusted (injection surface) — always fenced.
- The verbatim arXiv attribution + takedown link stay in the site footer.

## Commands

- Collector: `just status`, `just diverse`, etc. (recipes in
  `collector/justfile`, uv-managed; root `justfile` delegates). Corpus
  artifacts live under `corpus/` (gitignored).
- Backend (after #10): `uv run pytest`, `just be-lint`, `just ingest`.
  Golden set: `just golden` redrafts `evals/golden.jsonl` (model-checked, no
  human pass, D14 amendment 2026-09-30); `just evals-check` gates it;
  `just rewrites` writes one agent-model rewrite per question
  (`evals/rewrites.jsonl`); `just eval` scores BM25, vector, hybrid and
  rewrite + hybrid on it at the top 10 and top 50 (`--write-readme`
  refreshes the README table). Retrieval spine (#16): `just ask q="..."`. Agent REPL (#24):
  `just repl q="..."`. Chat API (#30): `just serve` (uvicorn dev server,
  `POST /api/chat`). Frontend (after #26): `pnpm build`, also run by the gate
  (#52 — `tsc` is not `next build` in export mode). After ANY route or
  response-model change run `just gen-openapi` — `just check` catches type
  drift but not schema drift, because `openapi.json` is typegen's input.
- Landing pipeline, in order: `just text --months <YYMM>…` (PDFs → the flat
  text tree; scope it, an unscoped run pulls the pre-2026 facet sample into
  the citation graph) → `just citations` (extract + resolve the citation
  graph) → `just frontier` (derive the index manifest, fetch and extract its
  papers) → `just index` (chunk, embed, rebuild corpus.db + chroma).
  `just thumbnails` stands outside that order: card images render on first
  request and cache as files (D19), so the recipe only warms the backlog. The
  manifest in `corpus/frontier.json` IS the page's scope — widen it via
  `frontier_top_cited`/`frontier_citers_per_work` in `config.py`, and expect a
  re-embed. Frontend routes: Explore at `/` (home: the
  whole-catalog filter, the one list that is not indexed-only, D16 amendment
  2026-09-16), the citation counts at `/citations`, arXiv's category
  census at `/trends`, the RAG demo at `/demo`
  (indexed papers, reader, agent).
- Deploy (#81): `just deploy` (compose up; ingress on loopback), `just
  deploy-tailnet` (publish via the host's tailscaled), plus `deploy-logs`,
  `deploy-down`, `deploy-reseed`. Runbook: `deploy/README.md`.
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
