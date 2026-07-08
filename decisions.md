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

## 2026-07-08 — traces.db gains `question`/`answer_text` so showcase replays reproduce the answer, not just the timeline (issue #30)

**Context:** #30 builds the chat route's REPLAY branch (D11: the site
degrades to a cached showcase session once the global daily cap is spent).
`traces.Run` carried tool-call records + tokens/cost but no answer text, so
a replay could reconstruct the tool-call timeline but not the final answer
— not "a still-good demo" (D11's own framing), just a timeline with no
punchline.
**Decision:** `runs` gains two `NOT NULL` columns, `question` (the user
message the run answered) and `answer_text` (the turn's final answer —
our own AI-generated text, §6c-compliant, never raw retrieved chunk text).
`traces.Run`, `record_run(...)`, and `_row_to_run` all extend to carry them;
`loop.py`'s `run_turn` (which already calls `record_run` internally) passes
`user_message` and the final `TurnResult.text` through, no other loop
change. `askrag/api/replay.py` reads `answer_text` back out as the
replayed turn's one `text` SSE event.
**Alternatives rejected:** a separate `showcase_answers` table keyed by
`run_id` (D13/§4c: "replays live in traces.db... no separate format, no
second store" — splitting the answer into a second table violates that
decision for no benefit, since every showcase row needs an answer 1:1);
storing the answer only for `showcase=1` rows (adds a conditional-NULL
column and a "how did this showcase get flagged after the fact with no
answer" failure mode — simpler to always capture it, it costs a few KB
per run in a `traces.db` that's already dev/prod ephemeral).
**Consequence:** `traces.db` is dev-only and regenerable (D13/§4c: no
migration path exists or is warranted) — `CREATE TABLE IF NOT EXISTS`
does not retrofit existing local databases, so a pre-#30 `traces.db` must
be deleted/moved aside once, not migrated; a fresh one picks up the new
schema on its first write. `tests/test_traces.py`'s `sample_run` fixture
and every other test file constructing `record_run(...)` calls updated to
pass the two new required fields.
Spec updated: no (§4c's "replays live in traces.db" decision already
covers this; `Run`'s exact column set was never spec-pinned, just the
one-store constraint, which this entry keeps intact).

---

## 2026-07-07 — `ui_action` is advisory/pre-validation, documented explicitly for #26's stream consumer (issue #24 review round 2)

**Context:** review round 1 on PR #64 flagged (non-blocking nit) that
`sse_events.translate()`'s `drive_ui` → `ui_action` mapping fires at
`TOOL_CALL` time on the model's raw args, before `drive_ui.run()` validates
the target against corpus.db — correct behavior per #24's own brief, but the
"treat `ui_action` as provisional, reconcile against the paired
`tool_result_summary`" contract only lived in the PR body, not anywhere a
future consumer would see it.
**Decision:** keep the behavior unchanged; document the contract on
`UiActionEvent` itself (`askrag/api/sse_events.py`) so #26's
`use-agent-stream.ts` inherits it by reading the type it consumes, not by
re-discovering it from a closed PR thread.
**Alternatives rejected:** deferring `ui_action` emission until after
`drive_ui` dispatch validates (would need `TOOL_RESULT`'s `AgentEvent` to
also carry the action's args, a `loop.py` change out of scope for #24 and
unmotivated — the paired `tool_result_summary(ok=False)` already surfaces a
rejected target one event later).
**Consequence:** no code behavior change; `sse_events.py`'s docstring is now
the durable source #26 reads from.
Spec updated: no (process-only; documents an existing, reviewed behavior).

---

## 2026-07-07 — `askrag/cli.py` is the single terminal entrypoint; `loop.main`/`_print_event` retired (issue #24)

**Context:** #23 shipped `loop.py`'s own `main()` + `_print_event()` as a
one-shot smoke CLI (`just smoke-agent`). #24's task brief names the REPL as
milestone 3's exit artifact and directs consolidating onto one CLI rather
than keeping two terminal entrypoints into the same loop.
**Decision:** `askrag/cli.py` is THE terminal entrypoint: no question arg
runs the interactive multi-turn REPL (threading `TurnResult.messages`
between turns, printing a live tool-call timeline via
`askrag.api.sse_events.translate()`, a running session cost, and
corpus.db-verified citations after each answer); one question arg runs a
single one-shot turn. `loop.py`'s `main()` and `_print_event()` are deleted
outright (shed, not aliased) along with the now-unused `argparse`/`sys`/
`telemetry` imports they were the only callers of. `just repl` (new) and
`just smoke-agent` (repointed) both call `askrag.cli` — the smoke recipe's
OpenRouter cheap-first behavior (decisions.md 2026-07-06) is unchanged,
only the module it invokes changed.
**Alternatives rejected:** keeping `loop.main` for one-shot smoke and adding
`cli.py` only for the interactive REPL (two entrypoints into the same loop
that would drift, exactly what "one CLI, one way" exists to prevent).
**Consequence:** `loop.py` no longer prints anything or touches
`telemetry`/`sys`/`argparse` — it is purely the library the CLI (and later
#40's chat route) calls into, which was already its intended shape (D2).
Spec updated: no (process-only; `sse_events.py`/`cli.py` are #24's own
Build-list files, already named in spec §4c).

---

## 2026-07-06 — OpenRouter becomes validation-only (cheap-first smoke); live serving reverts to direct Anthropic/Haiku, superseding 2026-07-05's OpenRouter-as-primary plan (issue #23, owner directive)

**Context:** 2026-07-05's "Live agent LLM: OpenRouter-routed model via env"
entry planned OpenRouter's OpenAI-compatible API as the LIVE agent's primary
provider (replacing D3's Haiku-on-Anthropic plan outright), with reasoning-
block round-tripping as a named build requirement for #22/#23. That wiring
was never built (neither #22 nor this PR touched an OpenAI-compatible
client). The owner redirected before #23 landed: validate the hand-built
loop against a CHEAP model first, keep prod serving on Haiku.
**Decision:** the loop's `ModelClient` seam is `anthropic`-SDK-shaped
throughout — no OpenAI-compatible client exists anywhere. `config.py` gains
`agent_api_base_url` (default `""` ⇒ real Anthropic, D3's Haiku), an
env-only `openrouter_api_key`, and `smoke_model` (`deepseek/deepseek-v4-flash`).
Setting `agent_api_base_url` routes the SAME `anthropic.Anthropic` client at
OpenRouter's **Anthropic-compatible** endpoint (not its OpenAI-compatible
one) — one client, config-only branching, no second SDK, no branching inside
`loop.py` itself (`anthropic_client_from_settings` is the only place that
looks at the setting). Two empirically-resolved integration details, recorded
because the docs left them ambiguous: (1) base_url is
`https://openrouter.ai/api` **without** a trailing `/v1` — the anthropic SDK
appends `/v1/messages` itself, so `.../api/v1` double-`/v1`s to a 404; (2)
auth is `auth_token=` (Bearer) via the SDK, not `api_key=` (x-api-key) —
OpenRouter documents Bearer, Anthropic's native header is x-api-key. Pricing
for cost accounting stays Haiku's (`agent_usd_per_mtok_*`) regardless of
which model actually served a smoke call — the smoke validates loop
plumbing, not billing, so its trace cost is an approximation by design.
Because the loop always appends `response.content` verbatim back into the
next call (the standard Anthropic tool-use round-trip, needed regardless of
provider), the "reasoning blocks must round-trip" requirement from the
superseded plan is satisfied as a side effect of ordinary tool-use handling —
it never needed special-casing once the client is Anthropic-shaped.
**Alternatives rejected:** building the OpenAI-compatible client as
2026-07-05 planned (never implemented; superseded before any code existed,
so there is nothing to migrate away from); smoke-testing directly against
Haiku first (defeats the "cheap-first" point of validating an unbuilt loop
before spending on the prod model).
**Consequence:** the 2026-07-05 "Live agent LLM: OpenRouter-routed model via
env" entry below is superseded — its OpenAI-compatible-API plan for the live
agent does not ship; treat it as historical context, not current behavior.
Running the live smoke needs a real `OPENROUTER_API_KEY` (coordinator/human
step); `just smoke-agent q="..."` documents how. Fake-model tests
(`test_loop.py`) are the PR's actual acceptance gate; the smoke is the
owner's separate confirmation, per the issue's acceptance checklist.
Spec updated: D3 (one-line note: a cheap OpenRouter model validates the loop
before Haiku spend; D3's prod decision — Haiku, direct Anthropic — is
unchanged).

---

## 2026-07-06 — #23 ships only the system-prompt quote-discipline instruction; the server-side ≤3-quote/≤50-word per-answer gate stays #30's job (issue #23)

**Context:** an #23 issue comment (carried forward from #22/#58) called the
per-answer quote-accounting gate a "hard acceptance gate... not optional" for
this issue. The 2026-07-06 `read_paper` decisions.md entry (below) already
moved that cap downstream to "answer-assembly (#23/#30)" once `read_paper`'s
own tool-level cap was removed as contradicting §6c row 1/D1. #23's own task
brief scopes the server-side gate out explicitly: building it needs verified
citations (which answer-assembly, not the loop, produces) and the issue's
own **Build** list names only `prompts.py`/`context_window.py`/`loop.py`.
**Decision:** #23 implements the quote-discipline **instruction** only
(`prompts.py`'s QUOTES paragraph: prefer paraphrase, keep verbatim quotes
short and quoted). It does NOT implement per-answer/per-conversation
quote-count enforcement — there is no answer-assembly stage in this PR to
enforce it in. The hard, server-side ≤3-quotes-per-paper/≤50-word cap (§6c
row 4) remains #30's responsibility, unchanged from the `read_paper` entry.
**Alternatives rejected:** bolting quote-counting onto `loop.py` now (the
loop only ever sees one turn's raw tool results, not an assembled answer with
resolved citations — the same reasoning the `read_paper` entry already used
to reject enforcing it at the tool boundary applies here too, one level up).
**Consequence:** none of this PR's user-facing surfaces exist yet (no route,
no frontend), so there is no shippable path that could return an unguarded
quote today; the gate is still required before #30 exposes one. Noted here
so the boundary is explicit rather than inferred from silence.
Spec updated: no (§6c's clarifying note already covers this from the
`read_paper` side; this entry just confirms #23 doesn't build the other end).

---

## 2026-07-06 — Agent loop context window: evict-only, not evict-then-summarize (issue #23)

**Context:** issue #23 named "evict/summarize stale tool results" as the
context-window mechanism without picking one.
**Decision:** v1 evicts only — the oldest still-live `tool_result` block is
replaced with a short `[evicted: earlier <tool> result]` stub, one block at a
time, until the running estimate fits `message_token_budget` or nothing
evictable remains. Summarization is not built.
**Alternatives rejected:** evict-then-summarize (an LLM call to summarize
stale context needs the model client mid-eviction, which breaks the
API-free test story — house rule, tests never call an LLM — and spends part
of the very token/cost budget the mechanism exists to protect); a rolling
window by message count instead of tokens (message count doesn't track
actual context cost — a single `read_paper` result can be worth many short
turns).
**Consequence:** `test_context_window.py` covers oldest-first ordering, the
current-turn/system-prompt exclusion, and the "nothing left to evict"
termination case. A pathological turn can still end up over budget once
every tool_result is stubbed — accepted, because `max_tool_steps_per_message`
is the real backstop against runaway turns, not eviction.
**Revisit trigger:** eviction demonstrably drops context an answer needed
(measured via eval failures traceable to a stubbed-out tool result).
Spec updated: no (D1/D2 already name "evict/summarize" as the mechanism
class; this entry just resolves which one v1 ships).

---

## 2026-07-06 — query_metadata prefactor: enum'd shapes replace raw model SQL, done before #23 (issue #60)

**Context:** #23's agent loop is about to become `query_metadata`'s first
model-facing consumer. Four reasons converged to reshape the tool before that
wiring happens rather than after: **security** — raw model SQL had already
produced a `randomblob` DoS (#57 review finding) and a blob-literal JSON crash
(#59 review finding); **portability** — the safety model was welded to sqlite
primitives (`set_authorizer`/`set_progress_handler`) with no Postgres analog,
blocking the D4 pgvector migration seam; **reliability** — an LLM authoring
SQL is error-prone where a typed op it picks from a closed menu is used
correctly; **clarity** — mirroring `drive_ui`'s existing discriminated-union
pattern is simpler than the authorizer/progress-handler machinery it replaces.
**Decision:** `query_metadata` is now a `drive_ui`-style `RootModel` over a
`Field(discriminator="op")` union of exactly three ops — `count_papers`
(filters: `category`/`year_min`/`year_max`/`has_license`; optional
`group_by: Literal["category","year","license","venue"]` resolving through a
server-side `{Literal -> column}` map, never string-interpolated; `None` →
scalar count, else → a top-N-bounded histogram), `paper_facets` (point lookup
by `paper_id` → title/primary_category/year/version/license/venue/n_chunks/
n_pages, raises on unknown id), `corpus_stats` (no params → n_papers/n_chunks/
year_min/year_max/n_categories). Every op runs one fixed parameterized SQL
template; there is no model-authored SQL path anywhere. Per-op frozen
dataclass results (`CountPapersResult | PaperFacetsResult | CorpusStatsResult`),
each with `to_model_payload()` (the #58 pattern). DELETED entirely, no
back-compat: `_make_authorizer`/`set_authorizer`/the `SQLITE_FUNCTION`
allow-list, `set_progress_handler` + its deadline, single-statement reliance,
`QueryMetadataArgs(sql=...)`, `_json_safe_cell`. Dead config removed:
`query_metadata_allowed_functions`, `query_metadata_timeout_seconds`;
`query_metadata_max_rows` repurposed and renamed
`query_metadata_histogram_max_groups` (the histogram top-N ceiling — the only
row-returning shape left to cap). The `mode=ro` corpus connection stays
(cheap defense-in-depth); with no model-authored SQL the injection/DoS surface
is gone by construction, not by a guard against it.
**Alternatives rejected:** keeping the authorizer/timeout machinery alongside
the new enum'd ops "just in case" (redundant — there is no SQL path left for
it to guard, and an unused security mechanism is itself a maintenance
liability); a fourth `list_papers` shape (speculative — not in the certain
core the issue named; further shapes are evidence-driven from #23's real
usage per the issue's "evidence-driven growth" note, never guessed).
**Consequence:** `tests/test_query_metadata.py` is fully rewritten — the old
SQL-injection/DoS-refusal tests are deleted (moot, no SQL surface); new tests
cover per-op correctness (scalar + histogram + facets + stats), filter
binding, off-enum `group_by` rejected by pydantic before execution, unknown
`paper_id` raising, and the union rejecting a free-form/`sql` field. `#23`
carries the evidence-channel note: its eval system prompt should invite the
model to state any metadata query it wished it had: recurring wishes get
promoted to new typed union variants later, never back to raw SQL.
Spec updated: §5 (`query_metadata` row rewritten: enum'd ops, no model SQL),
§6 (the "SQL injection (ish)" threat vector retired — replaced with "N/A",
enum'd parameterized shapes only).

---

## 2026-07-06 — §6c enforcement relocated: read_paper is the model-read path, not the verbatim-cap enforcer (owner directive, issue #58)

**Context:** the 2026-07-06 retrieval+tools coherence checkpoint (finding 1)
found `read_paper` applying the ANSWER/display cap (`quote_max_words=50`,
`max_quotes_per_paper=3`, §6c row 4) at the MODEL-facing tool boundary, so one
call returned ≤~150 words — contradicting §6c row 1 ("the model may read full
text via `read_paper`") and D1 ("read a specific paper deeper"), and
inconsistent with `search_corpus`, which already hands the model full
~1000-token chunks uncapped.
**Decision:** `read_paper` returns a page-ordered prefix of a paper's chunks
bounded by a new `read_paper_max_tokens` setting (default 16,000 — ≈20% of
`message_token_budget`, sized to cover a full short arXiv CS paper's chunks or
a substantial page range of a longer one while leaving room for further tool
calls in the same message). The ≤50-word/≤3-quote cap is removed from
`read_paper` entirely; it is NOT this tool's job. That cap governs verbatim
quotes surfacing in an ANSWER (§6c row 4) and moves downstream to
answer-assembly (#23/#30) and the frontend (#26), where it is now the hard
gate — §6b is unchanged throughout (extracted text from corpus.db only, never
PDF bytes).
**Alternatives rejected:** raising the tool's word cap instead of removing it
(still couples a display posture to a read tool, and any fixed word number is
arbitrary where a token budget maps directly to the model's real read cost);
leaving the cap at both the tool and answer-assembly (redundant enforcement
invites the two points drifting apart, and the tool-level cap was already
measured to cripple deep-read, defeating D1).
**Consequence:** `tests/test_read_paper.py`'s "no combination can reconstruct
the paper" invariant is replaced with: page-range bounding is honored, the
token budget is enforced, at least one span always returns even if it alone
exceeds the budget. #23/#30 must implement the per-answer ≤3-quotes-per-paper
gate (checkpoint Note A) — it no longer exists anywhere once this PR lands.
Spec updated: §6c (clarifying note: `read_paper`/row 1 is the model-read path,
not the row-4 enforcement point).

## 2026-07-06 — Per-worker git worktrees + Opus slice-boundary coherence auditor (owner directive)

**Context:** two problems surfaced landing #22. (1) Coordinator and workers
shared one git checkout, so the implementor's `git checkout -b` moved the branch
under the coordinator, and a coordinator harness commit landed on the PR branch
locally (caught before it reached the PR). (2) Per-PR review — even a strong
model — only sees the diff, so cross-issue drift, cross-layer contract rot, and
emergent boundary gaps (e.g. two `read_paper` calls breaching §6c per-answer
while each call is legal) have no owner.
**Decision:** (1) **Per-worker git worktrees.** Each worker runs in its own
detached worktree `.worktrees/<role>` (gitignored); the coordinator stays on
`main` in the primary repo and never git-collides with workers. Coordination
state (run-files, task logs) and the session jsonl are addressed absolutely /
by uuid, so a worker's worktree cwd doesn't hide them. `agent-spawn.sh` gained
`AGENT_BASE` (worktree ref) and `AGENT_MODEL`. (2) **Opus `auditor` role** runs
at each slice/epic boundary and before load-bearing issues, reads the whole
slice + spec + decisions + prior checkpoint, and writes
`docs/checkpoints/<date>-<slice>.md` (`COHERENT` / `NEEDS-WORK`, the latter
gating the next slice). Per-PR review stays Sonnet; load-bearing PRs (agent
loop, public API/SSE) get an added Opus review pass. Model tier is by blast
radius, not blanket — Sonnet demonstrably caught #57's single-opcode DoS, so
diff nuance is not the gap; whole-system coherence is.
**Alternatives rejected:** Opus on every PR review (burns limit for a
capability Sonnet shows); coordinator-commits-to-main-via-API only (divergence
bit us before); shared tree + discipline (just failed).
**Consequence:** `docs/sdlc.md` Worker harness section rewritten; auditor brief
added; `.worktrees/` gitignored; first checkpoint runs over the retrieval+tools
slice (#14/#16/#22) before #23.
Spec updated: no (process-only; the SDLC loop lives in `docs/sdlc.md`).

## 2026-07-06 — SDLC workers run as tmux-hosted claude CLIs for live observability (owner directive)

**Context:** the Agent/SendMessage subagent mechanism gave the coordinator no
live view into a running worker (edge-triggered "it finished" notifications
only) and gave the human no way to peek and catch a wrong action mid-flight;
subagents also lost re-messageability across a coordinator compaction (their
transcripts persist on disk, but the runtime handle does not cross the session
boundary). Observed twice while landing #16.
**Decision:** implementor/reviewer run as interactive `claude` CLIs in tiled
**panes of one `agents` window** in the human's **pre-existing** `rags` tmux
session (real name may be group-suffixed, e.g. `rags-0`), so every worker is
visible at once without switching windows. Four scripts under `scripts/`:
`agent-spawn.sh` (adds a titled pane per role, session-id pinned so the
coordinator knows the jsonl path, pane-id recorded so agent-send targets it;
fails loud if the session is absent — never creates it),
`agent-send.sh` (type + settle + Enter; short control messages only, big
context goes via files/PR), `agent-feed.sh` (human peek: one line per tool
call, MUTATE-flagged, read from the live-appended session jsonl — not scraped
from the TUI), `agent-pane.sh` (a worker opens a visible split pane for a
**long** run, teeing to `.claude/run/task-<label>.log`; short commands stay in
the worker's Bash). Machine channel = the on-disk jsonl; human channel = the
tmux window + feed. Compaction-by-respawn at task boundaries; durable context
stays in briefs + PRs + task files. Runs same-account (session limits are not
escaped, only made visible and cheap-to-resume); `ANTHROPIC_API_KEY` on the
workers is the escape hatch for true limit isolation, left unwired.
**Alternatives rejected:** headless `-p --output-format stream-json | tee`
(clean log but not human-watchable/steerable); scraping `tmux capture-pane`
(TUI grid is not a clean data channel); a second Claude subscription seat or
API-key billing now (cost, unjustified at this scale).
**Consequence:** briefs gained a working-surface rule (long→`agent-pane.sh`,
short→Bash); `docs/sdlc.md` gained a Worker harness section; `.claude/run/` is
gitignored runtime state.
Spec updated: no (process-only; the SDLC loop lives in `docs/sdlc.md`, not the
design spec).

## 2026-07-05 — Embeddings pivot to local-first: nomic-embed-text-v1.5 replaces Voyage as default (D5 second amendment, owner directive) (#13)

**Context:** the Voyage free tier turned out throttled to 3 RPM / 10K TPM for
no-payment-method accounts (previous entry below) — an 8.6h paced run for the
working corpus alone, and the same throughput cap would hit query-time in
production. The owner redirected: run embeddings **locally** by default,
keep Voyage working behind a flag for later.
**Decision:** `embedding_backend: Literal["local", "voyage"]` (default
`"local"`) in `config.py`; `make_backend()` is a literal two-branch dispatch
(§4d: no metaprogramming). Local backend is `sentence-transformers` running
**nomic-ai/nomic-embed-text-v1.5**, pinned to HF revision
`e9b6763023c676ca8431644204f50c2b100d9aab`, `truncate_dim=512`. Weights cache
under `corpus/models/` (gitignored — `.gitignore`'s existing `corpus/` rule
already covers it), never committed.
**Model choice, evaluated against the three stated criteria:**
(a) *Retrieval quality (English scientific text)*: nomic-embed-text-v1.5
publishes MTEB retrieval numbers including `ArxivClusteringP2P`/`S2S`
directly relevant to this corpus (HF model-index, checked 2026-07-05); no
sub-150M-parameter English-retrieval model found beats it on MTEB while also
meeting (b) and (c) below — checked against bge-small-en-v1.5 (33M, native
384 dims, no MRL to 512 — disqualified on (c)), gte-modernbert-base (149M,
~55.3 MTEB retrieval, no confirmed native 512-dim MRL), snowflake-arctic-
embed-m-v2.0 (305M, stronger retrieval but 2–3x the param budget), Qwen3-
Embedding-0.6B (600M) and jina-embeddings-v3 (570M) (both stronger but 4–5x
over budget), nomic-embed-text-v2-moe (475M total/305M active, multilingual-
focused — English BEIR ≈52.86, *lower* than v1.5's English MTEB). Models
that do beat v1.5 on raw retrieval are all 2–4x its parameter count, which
matters directly for (b).
(b) *Query-time CPU feasibility*: 137M parameters — the same model runs
query-time embedding inside the FastAPI process on the production VPS once
retrieval lands (#16), CPU-only, no GPU on that box. This is the load-bearing
argument for staying in the 30–120M-ish band rather than chasing raw MTEB
rank; ingest-time speed doesn't matter (Mac + MPS, one-time job) but
query-time speed on a small VPS does, every request.
(c) *512 dims via MRL*: the model card documents a trained (not just
truncated) Matryoshka checkpoint table — 768d: 62.28 MTEB, 512d: 61.96,
256d: 61.04, 128d: 59.34, 64d: 56.10 (huggingface.co/nomic-ai/nomic-embed-
text-v1.5, checked 2026-07-05) — 512 dims costs 0.32 points versus native
768, negligible. D5's 512-dim pin holds unchanged.
Nomic's asymmetric retrieval convention is mandatory, not optional: ingest
prepends `search_document: `, the query side (#16) MUST prepend
`search_query: ` or recall silently degrades — both prefixes are config
knobs (`embedding_doc_prefix`/`embedding_query_prefix`) read by both sides.
**Dependency gate — sentence-transformers==5.6.0** (measured 2026-07-05):
*Popular:* 18,878 GitHub stars (huggingface/sentence-transformers, via GitHub
API), 16.25M lifetime downloads of nomic-embed-text-v1.5 alone on the HF Hub.
*Maintained:* latest release 5.6.0 uploaded 2026-06-16 (PyPI), repo last
pushed 2026-07-03 (GitHub API) — Hugging Face org, human-reviewed merges.
*Security:* `pip-audit` (via `uvx pip-audit`, synced backend env) — no known
vulnerabilities; ships as wheels, no install-script surface; canonical HF
name, no typosquat risk. *Pinned:* `==5.6.0`. **PASS.**
**Dependency gate — torch==2.12.1** (measured 2026-07-05): *Popular:*
101,518 GitHub stars (pytorch/pytorch). *Maintained:* 2.12.1 uploaded
2026-06-17 (PyPI), repo pushed 2026-07-05 (GitHub API) — Meta/PyTorch
Foundation governance. *Security:* same `pip-audit` run, clean; wheel-only
install. *Pinned:* `==2.12.1`. **PASS.** (pypistats.org download-rank checks
were attempted but rate-limited (HTTP 429) on 2026-07-05; GitHub stars +
PyPI/HF metadata above are the substitute evidence — both packages are
unambiguously top-tier by any measure, so the gate holds despite the gap.)
*Alternatives rejected:* ONNX Runtime direct (skips sentence-transformers'
prompt/pooling/MRL-truncation handling — reimplementing that correctly for
one model is the kind of cleverness the gate exists to avoid); staying on
Voyage only and just fixing the pacing (doesn't solve the production
query-time throughput problem, which is the deeper reason for this pivot).
**Per-model artifact keying (the owner's core requirement for this pivot):**
every embedding artifact is now keyed by `embedding_model_slug` (short model
name + dims) so two models' vectors can never mix: `corpus/vectors/
<slug>.parquet`, shard dir `corpus/vectors/<slug>_shards/`, and the parquet
FILE METADATA additionally carries full provenance (model, revision, dims,
backend, created_at) via `EmbeddingProvenance`; `read_vectors()` refuses a
slug mismatch rather than silently reading another model's vectors. The
pre-existing Voyage partial shards moved under `voyage-4-lite_512_shards/`
under the same convention. Downstream: #14 keys Chroma collections by the
same slug; #18 tags eval runs by it — both issues carry matching coordinator
notes.
**Consequence:** the corpus embed run is now $0 (previously ~$0 net of the
Voyage free quota, but throttled); the tradeoff is CPU cost at query time
on the production VPS instead of an API call — untested until #16 lands and
is measured on real request latency. Voyage stays fully wired behind
`embedding_backend=voyage` for a future paid-tier or eval-driven swap; its
tests, pacing config, and decisions.md history are unchanged.
**Revisit when:** a paid embeddings tier enters the budget (Tier-1 billing
addresses the throughput problem outright), or #18 evals show a paid/larger
model retrieves meaningfully better than nomic-v1.5 on this corpus, or #16's
measured query-time CPU latency on the target VPS spec is unacceptable (in
which case a smaller model, not a cloud API, is the first thing to try given
the throughput argument that motivated this pivot).
Spec updated: D5 (second amendment), §4b table (Embeddings + Vector archive
rows), §4c tree (`corpus/vectors/<model_slug>.parquet`).

---

## 2026-07-05 — Dependency gate: pyarrow==24.0.0 (vectors.parquet, D5) (#13)

**Context:** D4/D5 and the §4c tree name `corpus/vectors.parquet` as the
embedding archive, but §4b listed no parquet implementation; pyarrow entered
the lockfile in PR #53 without a gate record (review finding, coordinator-
approved contingent on this record).
**Gate record — pyarrow 24.0.0** (all numbers measured 2026-07-05):
*Popular:* 390,713,980 PyPI downloads last month (pypistats.org) — top-tier;
apache/arrow 16,904 GitHub stars. *Maintained:* 24.0.0 is the latest release,
uploaded 2026-04-21 (PyPI), Apache Arrow project (ASF governance,
human-reviewed merges). *Security:* `pip-audit` on the synced backend env —
no advisories against pyarrow; installs from binary wheels (the wheel format
has no install-script hook), canonical name from the Apache project, no
typosquat surface. *Pinned:* `==24.0.0`. **PASS.**
*Alternatives rejected:* fastparquet (a fraction of the adoption, no Arrow
interop); duckdb (a whole query engine for one read/write path); polars
(dataframe library where only the Arrow storage layer is needed).
*Side observation for the coordinator:* the same audit flags pre-existing
`chromadb 1.5.9` → PYSEC-2026-311 (no fix version published yet) — on main
before this PR, tracked outside it.
Spec updated: §4b table (Vector archive row).

---

## 2026-07-05 — Embeddings: Voyage AI free tier replaces OpenAI (owner directive 2026-07-05) (#13)

**Context:** D5 defaulted to OpenAI text-embedding-3-small @512d (~$2–13
one-time). The owner directed the pivot to Voyage AI, whose free tier grants
200M tokens per current-generation model. Verified against docs.voyageai.com
on 2026-07-05: `voyage-4-lite` is the cheapest current text model with
`output_dimension=512` support ($0.02/Mtok list, 200M free tokens, 1,000
inputs / 1M tokens per request; the documented 2,000 RPM / 16M TPM table is
Tier 1, which requires a payment method on file — see measured correction
below). voyage-3.5-lite — the model D5 originally named as the alternative —
is the same list price but gets **no** free quota as a superseded model.
**Decision:** embed with `voyage-4-lite` at 512 dims via raw httpx against
`POST /v1/embeddings` (httpx is §4b pre-approved; one endpoint does not
justify the `voyageai` package — the `openai` dep leaves the lockfile, this
was its only consumer). Corpus chunks send `input_type="document"`; the query
side (#15) must send `input_type="query"`.
**Frugality consequence:** while on the free tier, spend discipline is a hard
constraint: tests never call the API (faked backend + MockTransport), backoff
honors Retry-After and never retry-storms, `--estimate` (no key, no network)
prices every run first, and full runs need an explicit owner/coordinator go.
The working corpus (~4.5M cl100k tokens) and even the full corpus (~80–100M)
fit inside the 200M free quota, so the expected one-time cost is $0. Chunk
`n_tokens` remain cl100k_base counts — estimates and batch caps carry margin
because Voyage bills on its own tokenizer; billed truth is API-reported usage
(measured ratio on real chunks 2026-07-05: 1.009 Voyage per cl100k token).
**Measured correction (2026-07-05, first full run):** our no-payment-method
account gets **3 RPM / 10K TPM** (stated verbatim in Voyage's 429 body; the
docs publish no sub-Tier-1 numbers). Any batch over ~10k tokens can never
pass, which 429'd the first run's 100k-token batches permanently. Config
defaults now fit the unpaid tier: 9,000-token batches + 62s inter-batch pause
(`embed_batch_pause_seconds`) ≈ 8.7k tokens/min → the working corpus takes
~8.6 h, resumable throughout. Tier 1 (payment method added, still $0 via free
tokens) would cut this to minutes — the owner's call, not ours.
**Alternatives rejected:** staying on OpenAI (real dollars for no quality
argument yet); `voyageai` SDK (new dependency for one POST); voyage-3.5-lite
(no free quota).
**Revisit trigger:** Voyage free-tier terms change or quota exhausts;
milestone-2 evals (#19) show a better-retrieving model worth paying for; or
query-time latency/outage behavior forces a second provider.
Spec updated: D5 (amendment), §4b table (Embeddings row).

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

---

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
