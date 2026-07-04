# askRAG — agentic RAG over the arXiv corpus (design spec)

**Date:** 2026-07-04
**Status:** Approved direction, pending final review
**Corpus:** 6,460 arXiv CS papers / 11.6 GB PDFs (2007–2026, cs.CL-heavy), indexed in
`arxiv.db` with title/abstract/authors/categories + five diversity facets
(`authority`, `niche_idf`, `author_novelty`, `revisions`, `venue_rigor`).
Produced by `arxiv_ingest.py` (see the [collector README](../../../README.md)).

## 1. Goal

A **publicly deployed portfolio project** whose message is "I know RAG — here is
the demo, here is the architecture, and here is why every piece was chosen."
The deliverable is three things at once:

1. A live site a recruiter can click with zero friction.
2. A repo an engineer can read where every load-bearing decision is deliberate.
3. A write-up with eval numbers backing the architecture claims.

### Non-goals (v1)

- Live corpus updates in production (frozen snapshot ships; see D12).
- Multi-tenant accounts, saved chats, personalization. Sessions are ephemeral.
- Table/equation extraction and computation over paper *contents* (v2 candidate).
- Serving our own PDF copies (licensing; see D9).
- Horizontal scale. This is engineered for one small VPS, on purpose (D4, D13).

## 2. Product shape

The **primary surface is a corpus explorer**, not a chatbot:

- Browse/filter/search 6,460 papers by category, year range, and the five facets.
- Open a paper → split view: **PDF embedded from arxiv.org** + our extracted
  text with chunk-level anchors.
- The **agent is a side panel**. It answers questions with citations, and it can
  *drive the explorer* through a constrained tool (open paper, jump to page,
  apply filters).
- The agent's work is visible: a live tool-call timeline (searched → read →
  analyzed) and a running token/$ badge per conversation. The architecture is
  the demo.

## 3. Decision records

Every load-bearing decision, in one format: **Decision / Why / Rejected /
Risks accepted / Revisit when**. The "revisit when" triggers are the contract:
none of these choices are permanent, but changing one without hitting its
trigger is churn, not engineering.

---

### D1. The agent feeds itself; the harness never stuffs context

**Decision.** Retrieval is a *tool the model calls*, not a pipeline stage. The
model decides when to search, what to search for, when to reformulate, when to
read a specific paper deeper, and when it has enough to answer. The harness
does everything around that loop: executes tools, keeps context bounded by
evicting/summarizing stale tool results, enforces a step budget (~8 tool calls
per user message), accounts tokens, and stops cleanly.

**Why.** (a) It is the honest meaning of "agentic RAG" — one-shot
retrieve-then-generate can't do multi-hop questions ("compare how X is treated
in the two most-cited 2019 papers vs recent work"), and multi-hop is exactly
what the demo must show. (b) Query reformulation by the model beats any static
query we could construct from the user message. (c) It makes the tool-call
timeline UI meaningful — there is a genuine decision process to display.

**Rejected.**
- *Harness-fed classic RAG* (embed user message → top-k → stuff → generate):
  cheaper and more predictable, but it demonstrates 2023-era RAG and caps the
  demo at single-hop questions.
- *Hybrid router* (classifier picks classic-RAG path for simple questions,
  agent path for hard ones): a real production pattern, but it doubles the
  surface area to build, test, and explain. Noted as the v2 cost optimization.

**Risks accepted.** Latency (multi-step loops take 5–20 s; mitigated by
streaming the timeline so waiting is watchable). Cost variance per message
(mitigated by step budget + hard token budget per message, D11). The model may
retrieve badly on some phrasing (mitigated by eval-tuned tool descriptions —
tool descriptions are prompts and get iterated like prompts).

**Revisit when.** >30% of eval questions are single-hop AND cost is the
binding constraint → add the router. If p95 latency exceeds ~25 s → cap steps
harder or add a fast path.

---

### D2. Hand-built agent loop on the raw Anthropic API — no framework, no SDK

**Decision.** The loop is ~200 lines we own: messages array, tool dispatch,
context-window management, budget enforcement, SSE event emission. Direct
`anthropic` Python client, nothing between us and the API.

**Why.** The stated showcase goal is *"I understand agents deeply."* A reviewer
reading this repo should find the loop, the eviction policy, the injection
fences, and the budget accounting as explicit code — not as framework
configuration. Every hardening claim in the write-up points at a line we wrote.
The write-up will include an honest "what the Claude Agent SDK / LangGraph
would have given us" section, which is only credible because we built the parts
ourselves.

**Rejected.**
- *Claude Agent SDK*: production-grade loop, sandboxing hooks, streaming for
  free — but it makes the most interesting 20% of the project someone else's
  code. Right choice for shipping product; wrong choice for this portfolio goal.
- *LangChain / LangGraph / deepagents*: demonstrates framework fluency but
  reads as glue code to senior reviewers, and debugging abstraction layers
  would cost more than writing the loop.
- *Vercel AI SDK*: would force the TS-everywhere stack rejected in D13.

**Risks accepted.** We re-implement solved problems (retries, streaming
plumbing) and will hit edge cases SDKs have already fixed — accepted as
tuition; the loop is small enough to debug. Provider lock-in is shallow: the
loop's tool-use shape ports to any provider in a day.

**Revisit when.** This stops being a portfolio piece and becomes a product
(then adopt the SDK), or the loop grows past ~500 lines of accidental
framework — that's the sign we're rebuilding an SDK badly.

---

### D3. Model: Claude Haiku 4.5 for the agent; a strong model only offline

**Decision.** Haiku 4.5 (`claude-haiku-4-5-20251001`, $1/M in, $5/M out) runs
the live agent loop, with prompt caching on the system prompt + tool
definitions. Stronger models are used only offline where cost is one-time:
drafting the golden eval set and as the eval judge.

**Why.** The $20/mo ceiling (D11) makes this arithmetic, not taste: a
5-step agentic turn is ~50k input (mostly cache reads at $0.10/M) + ~2k output
≈ **$0.02–0.08 per message**. A $0.50/day cap then buys 10–25 real
conversations daily — enough for a portfolio site. Sonnet-class would cut that
by ~3–5×. Haiku 4.5 is genuinely competent at tool use, and a visible-reasoning
UI flatters a fast model (snappy timeline) more than a slow smart one.

**Rejected.** *Sonnet 4.5 live* (better answers, blows the budget at the same
cap — fewer conversations/day); *open-weights on the VPS* (a $5 VPS cannot
serve a competent tool-use model; a GPU box is 10× the budget).

**Risks accepted.** Some hard multi-hop questions will get mediocre syntheses.
Mitigated by: the eval harness measures this honestly, and the write-up states
the cost/quality tradeoff as a *decision* with numbers — which is worth more
portfolio-wise than silently better answers.

**Revisit when.** Eval answer-quality scores are embarrassing on >20% of the
golden set → try Sonnet behind the same caps and publish the delta. Model
prices drop (they do) → re-run the arithmetic.

---

### D4. Storage: SQLite (metadata + FTS5) + embedded Chroma (vectors) — no database server

**Decision.** Two embedded stores, zero server processes. SQLite extends the
existing `arxiv.db` pattern: `papers` (already exists), `chunks` (text,
paper_id, section, page span), FTS5 virtual table for BM25. Vectors live in
**Chroma in embedded mode** (`PersistentClient` in-process with FastAPI, HNSW
index on disk), keyed by the same chunk ids as SQLite. ~100k × 512-dim
vectors is comfortably inside Chroma's embedded sweet spot. Backup is copying
a directory. Prod opens everything read-only.

**Why.** At this scale a database *server* is pure liability: another process
to run, secure, and migrate on a $5 VPS, purchasing performance we cannot use.
Chroma embedded keeps that no-server property while giving a real ANN index,
a purpose-built vector API (metadata-filtered queries built in), and a
recognizable line on the stack list. The write-up frames this as the thesis
of the whole project — **right-sized engineering** — and names the exact
migration trigger below, which proves the choice was made with eyes open
rather than by default.

**Rejected.**
- *Postgres + pgvector*: **explicitly deferred, not rejected** — it is the
  designated successor and the correct answer at 10× scale or when prod needs
  writes. Adopting it now buys ops burden with zero user-visible benefit.
- *Managed vector DBs (Pinecone/Weaviate/Qdrant Cloud)*: monthly cost against a
  $20 ceiling, network hop on every query, and "I paid a vendor" is the
  opposite of the demo's message.
- *sqlite-vec (everything in one file)*: the maximally-minimal option and it
  would work here (brute force at 100k vectors is <100 ms), but it's a young
  extension, and splitting vectors into Chroma keeps the vector layer
  swappable behind an interface — which is exactly the seam the pgvector
  migration will use.
- *Chroma client/server mode*: reintroduces the server process embedded mode
  exists to avoid.

**Risks accepted.** Two stores means the ingest pipeline is the only thing
keeping SQLite and Chroma consistent (mitigated: both are rebuilt together as
one artifact by `just ingest`; chunk id is the shared key; prod is read-only
so they cannot drift). Chroma's on-disk format changes across versions —
pin the version; vectors are also archived as a parquet artifact of the
ingest pipeline, so rebuilding any index layer is a re-load, not a re-embed.

**Revisit when.** Corpus >~50k papers or ~1M chunks, or query p95 >300 ms, or
prod needs concurrent writes (live updates, D12) → Postgres + pgvector
(vectors *and* metadata converge into one server then).

---

### D5. Embeddings via API (default: text-embedding-3-small @ 512d), not local

**Decision.** Embed ~80–100M corpus tokens through an embeddings API at 512
dims. Default is OpenAI `text-embedding-3-small` truncated to 512 dims
(native Matryoshka support, $0.02/M → ~$2 for the corpus); voyage-3.5-lite is
the named alternative if milestone-2 evals show it retrieving better on this
corpus. One-time cost **$2–13**. Query-time embeddings are the same API —
pennies/month. Vectors archived to parquet (see D4).

**Why.** The corpus embed is hours and single-digit dollars; a local model on
the Mac is a day-plus of babysitting to save ~$10, and — the real cost — the
**prod VPS would then need to run the same model for query embeddings**,
eating the RAM budget of a small box. Re-embedding after a chunking change
(evals will force at least one) is trivial money, which keeps the eval loop
honest: we'll actually re-embed rather than rationalize the current chunking.

**Rejected.** *Local sentence-transformers (bge/gte)*: free and offline, right
choice at 100× the token volume or under data-privacy constraints; neither
applies. *Matryoshka/quantization games*: 512 dims already fits; optimizing
further is effort without a bottleneck.

**Risks accepted.** Vendor dependency for query embeddings (an API outage
degrades search to FTS5-only — the hybrid design in D8 means the site limps
rather than dies). Model deprecation forces a re-embed (~$10, annoying not
scary).

**Revisit when.** Query embedding spend exceeds ~$5/mo (it won't at this
traffic), or the vendor deprecates the model, or a local model wins on the
eval set by enough to matter.

---

### D6. PDF extraction: PyMuPDF4LLM, with a skip list, not a GPU parser

**Decision.** Extract all PDFs to markdown with page mapping using
PyMuPDF4LLM. Failures (scanned, corrupt, encrypted — expect a low single-digit
percentage) go to a recorded skip list, visible in ingest stats, not silently
dropped. Per-paper extraction artifacts (JSON: sections, page offsets) are
cached so re-chunking never re-parses.

**Why.** CPU-fast (the whole corpus in ~1–2 hours on the Mac), no GPU, and for
arXiv's born-digital LaTeX PDFs the text quality is genuinely good. The known
weakness — tables and math render poorly — does not block v1, whose retrieval
targets prose.

**Rejected.** *marker / docling* (GPU-class layout parsers): materially better
tables/structure, at 10–50× the wall-clock on this hardware. This is the v2
unlock for the "computation over paper contents" feature, not a v1 need.
*Unstructured.io / API parsers*: per-page pricing across 11.6 GB is real money
for quality we don't need yet.

**Risks accepted.** Table/equation questions will retrieve poorly; the eval
set will include a few such questions *on purpose* to measure (and honestly
report) the floor. Two-column edge cases may garble reading order in a
minority of papers.

**Revisit when.** Building the v2 table-computation feature, or evals show
extraction (not retrieval) is the dominant failure mode on prose questions.

---

### D7. Chunking: section-aware, ~1,000 tokens, overlap, page-anchored

**Decision.** Split on the markdown section structure from D6; pack sections
into ~1,000-token chunks with ~15% overlap; never cross section boundaries;
every chunk carries `(paper_id, section_title, page_start, page_end)`. The
title + abstract of each paper is additionally embedded as its own
paper-level chunk (cheap coarse retrieval + powers explorer semantic search).

**Why.** Section-awareness keeps chunks semantically whole (a methods chunk
isn't half-conclusion). Page anchors are what make citations *verifiable* —
the UI jumps the PDF to the cited page (D9), which is the trust moment of the
demo. 1,000 tokens balances recall against context-stuffing in an agentic
loop where the model may pull many chunks.

**Rejected.** *Fixed-size sliding window* (ignores structure we already
extracted); *semantic/embedding-based chunking* (an extra embedding pass and a
research-flavored dependency for marginal gain at this corpus quality);
*late chunking / ColBERT-style* (index size and complexity unjustified before
a plain baseline is even measured).

**Risks accepted.** All chunking constants are guesses until evals run —
which is fine, because D5 makes re-embedding cheap and the constants live in
one config.

**Revisit when.** Eval recall@k plateaus below target and error analysis
points at chunk boundaries; then sweep size/overlap as an eval experiment.

---

### D8. Retrieval: hybrid (vector + BM25 + RRF), filters pushed down; rerank only if evals demand it

**Decision.** `search_corpus` runs vector search (Chroma) and BM25 (FTS5)
in parallel, fuses with reciprocal rank fusion, applies metadata filters
(category, year, facets — pushed into Chroma's `where` and SQL respectively),
returns top-k chunks with provenance. A
rerank stage (voyage rerank or LLM listwise) is built as an optional flag and
ships **only if** it beats the baseline on evals by a margin worth its latency.

**Why.** BM25 catches what embeddings miss on this corpus — exact model names,
dataset names, author names, acronyms ("RLHF", "BLEU") — and it's nearly free
since FTS5 is already in the file. RRF is fusion without tuning weights.
Filters-in-SQL exploits the facet columns the collector already computed.
Making rerank eval-gated (not default-on) is itself a demonstrated decision:
stages must pay rent.

**Rejected.** *Vector-only* (the classic demo shortcut; fails on exact-match
queries and we'd be publishing evals that show it); *rerank always-on*
(latency + cost before evidence); *graph RAG / knowledge graphs* (a different
project; named in the write-up as deliberate non-scope).

**Risks accepted.** RRF constants and k values are defaults until measured.
Hybrid means two code paths to keep correct — accepted, that's the point of
the eval harness.

**Revisit when.** Evals show one leg contributes nothing (drop it and say so —
negative results are portfolio material too), or rerank's margin justifies its
latency.

---

### D9. PDF viewer embeds arxiv.org; we never serve our PDF copies

**Decision.** The viewer loads `arxiv.org/pdf/<id>` in an iframe, using
`#page=N` fragments for citation jumps. Our extracted text (which we *do* own
the right to process) renders alongside with chunk-level highlights. The
11.6 GB corpus never deploys; prod ships only the index artifacts —
`corpus.db` + `chroma/`, ~1–2 GB total with text and vectors.

**Why.** Most arXiv papers are under arXiv's non-exclusive license, which does
**not** grant redistribution — publicly serving our copies is legally gray,
and a portfolio project is exactly where you don't want a takedown story. The
side benefits are real: prod storage drops ~85%, and "why isn't the corpus in
prod" becomes a licensing-awareness paragraph in the write-up.

**Rejected.** *Serve local copies* (best latency and deep-link control;
rejected on licensing); *text-only, no PDF* (simplest; loses the split-view
trust moment where the citation lands on the actual page); *PDF.js rendering
arXiv-fetched bytes* (needs permissive CORS from arXiv — not counted on; see
risk below).

**Risks accepted.** arXiv may set `X-Frame-Options`/CSP that blocks iframes,
or rate-limit hot traffic. **Fallback ladder, designed-in:** iframe → PDF.js
via our thin caching proxy (single-file, short-TTL cache — closer to
"browsing arXiv" than "redistributing a corpus", still gray, documented) →
extracted-text-only view with an "open on arXiv" button. The split view keeps
our text pane primary so the demo survives any rung. `#page=N` precision
varies by browser viewer — citations also always show section + our text
anchor, so page-jump is enhancement, not correctness.

**Revisit when.** The iframe rung fails in testing (drop a rung), or the
corpus ever shifts to verified CC-BY-only papers (then self-hosting is clean).

---

### D10. Sandbox: fresh Docker container per execution, no network, read-only data

**Decision.** `run_python(code)` runs agent-written analysis code in a
per-execution Docker container: `--network none`, read-only mounts of the
metadata DB + extracted-text parquet, 1 CPU / 512 MB / 30 s wall limits,
tmpfs workspace, non-root user, container destroyed after the call. Returns
stdout + any matplotlib PNGs, rendered in the panel. Pre-baked image with
pandas/matplotlib/numpy (no pip at runtime — no network anyway).

**Why.** The sandbox exists for one demoable job: **corpus analytics** —
"plot venue-rigor of cs.CL papers 2010–2026" — which is the moment the demo
visibly exceeds chatbot-with-search. Fresh-container-per-call is also the
entire cross-user isolation argument: there is no state to leak. No-egress is
the entire exfiltration argument: even fully injection-compromised code has
nowhere to send anything and nothing writable to persist.

**Rejected.** *No sandbox in v1* (tempting for speed, but code execution is
load-bearing for both the demo and the "I know agent infra" claim); *gVisor/
Firecracker* (real hardening, disproportionate ops for a demo where the
container's blast radius is already read-only public data; named as the
production-grade answer in the write-up); *hosted sandboxes (Vercel/Modal/E2B)*
(per-execution pricing against a $20 ceiling, and outsources the most
interesting infrastructure); *warm container pool* (premature — cold start
~1–2 s is acceptable inside a visible timeline).

**Risks accepted.** Container escape via kernel exploit is theoretically
possible — accepted because the box holds only public data and the write-up
says exactly that (an honest threat model outranks pretend invulnerability).
Docker adds ~1–2 s latency per execution. The VPS must run Docker (memory
overhead on a small box — sized into D13).

**Revisit when.** Any writable or private data enters the sandbox's reach →
gVisor minimum. Execution volume makes cold starts the UX bottleneck → warm
pool.

---

### D11. Access: free and anonymous, budget-capped, degrading to cached replays

**Decision.** No accounts. Layered caps, all enforced server-side:
per-message token budget → per-session budget (~15 messages) → per-IP daily
budget → **global daily spend cap (~$0.50/day)**. When the global cap trips,
the agent panel switches to **replayable cached showcase sessions** (recorded
real traces, played through the same timeline UI) with a banner saying the
live budget is spent — the site degrades to a still-good demo instead of an
error page. Cloudflare free tier in front (rate limiting, bot filter);
Turnstile only on the live-agent endpoint and only if abuse materializes.

**Why.** The audience is recruiters and engineers following a link; any
login wall loses most of them. The worst case must be bounded by
construction: $0.50/day ≈ $15/mo ceiling on LLM spend regardless of what any
abuser does. The degrade path turns the failure mode into a feature — cached
replays are *also* how the site demos at zero marginal cost forever.

**Rejected.** *Login-gated live agent* (near-zero risk, near-zero audience);
*BYO API key* (friction plus handling other people's secrets); *fully open,
rate-limits only* (rate limits bound requests, not tokens — an agentic
endpoint's cost per request varies 100×, so token budgets are the only honest
cap).

**Risks accepted.** A determined person can exhaust the daily budget in
minutes and deny live access to others — accepted, because the denial-of-
wallet is capped and the replay fallback keeps the site alive. IP-based
budgeting is weak against rotation — accepted; the global cap is the real
backstop, the per-IP layer just keeps one visitor from accidentally hogging.

**Revisit when.** Real traffic regularly exhausts the cap (a good problem:
raise it, or add opt-in BYO-key for power users). Abuse defeats Cloudflare
free tier → Turnstile everywhere.

---

### D12. Frozen corpus snapshot in prod; the update pipeline stays offline

**Decision.** Prod serves a build-stamped snapshot (`corpus 2026-07`,
shown in the footer). The existing `update` recipe keeps working locally;
refreshing prod = re-run ingest → upload new SQLite file → restart.

**Why.** Live updates would drag the whole ingest chain (download → extract →
chunk → embed → index) onto the VPS, force concurrent writes (breaking D4's
read-only posture), and add a moving part that can silently corrupt the demo
while nobody is watching. A dated snapshot costs one sentence of honesty in
the UI.

**Rejected.** *Daily cron on the VPS* (ops burden, D4 trigger, embed API key
on the box); *event-driven refresh* (engineering a pipeline the demo doesn't
need).

**Risks accepted.** The corpus stales visibly (the newest papers are the ones
visitors may ask about). Mitigated by the banner and by quarterly manual
refreshes being a 30-minute chore.

**Revisit when.** The project pivots from portfolio to product, or manual
refreshes exceed monthly cadence — then build the pipeline *as* the next
portfolio chapter (it's D4's pgvector trigger too).

---

### D13. Stack: FastAPI (uv) + Next.js, self-hosted on one Hetzner-class VPS, Caddy, SSE

**Decision.** Python FastAPI backend managed with **uv** (agent loop, tools,
budgets, SSE event stream), **Next.js frontend** (pnpm; full stack detail in
§4b) built as a **static export** (`output: 'export'`) and served by Caddy
(auto-TLS) — the app is client-rendered against the FastAPI API, so no Node
process runs in prod unless a future feature demands SSR. One ~$5–8/mo VPS
(2 vCPU / 4 GB — sized for Docker headroom per D10), Cloudflare DNS in front.
Streaming is **SSE, not WebSockets** — the agent event flow is strictly
server→client. Deploy = `docker compose up` via a `just deploy` recipe.
Traces land in a local SQLite `traces.db` (every agent run: tool calls,
tokens, cost, latency) — it feeds the timeline UI, the eval harness, and a
private admin page showing daily spend against cap.

**Why.** The repo is already Python; the ingest code and its `just` culture
carry straight over. Next.js is the frontend ecosystem employers recognize
and where shadcn/Tailwind v4 tooling is first-class; static export keeps its
footprint on the VPS at "files behind Caddy," which preserves the flat-cost,
no-extra-process posture. A flat-cost VPS is the only hosting model where a
public agentic endpoint can't surprise-bill you — usage-priced serverless
*is* the denial-of-wallet attack surface (compute dimension of D11). Full
control of Docker is required by D10; most PaaS sandboxing options replace
our sandbox story with a vendor's.

**Rejected.** *Vercel-hosted Next + managed services* (slicker DX; moves
costs to usage-based and outsources the sandbox — Next.js the framework
stays, Vercel the host goes); *Vite SPA* (lighter, but loses the Next
ecosystem alignment the portfolio wants to signal); *SSR/Node runtime in
prod* (a second server process with no current feature paying for it —
adopt only if a real SSR need appears); *Cloudflare Workers stack* (cheapest
at scale, most exotic to build/debug, no Docker); *Kubernetes anything* (a
joke at this scale, but named because the write-up should say why not).

**Risks accepted.** We are the ops team: unattended-upgrades, Caddy, fail2ban,
backups (one SQLite file to object storage nightly). Single box = single
point of failure — accepted for a demo; downtime costs nothing but pride.

**Revisit when.** Sustained real usage or a second service appears →
managed Postgres (D4 trigger) and a second box. The demo outgrows one
maintainer's patience for ops → PaaS with the sandbox story redesigned.

---

### D14. Eval harness ships in v1 and gates retrieval decisions

**Decision.** ~50-question golden set: drafted by a strong model against
sampled chunks (question + expected source paper/passage), **hand-verified**
before it counts. Two layers: (1) retrieval metrics — recall@k, MRR — run
per configuration (vector-only / BM25-only / hybrid / ±rerank, chunk-size
sweeps); (2) end-to-end LLM-judged faithfulness + citation accuracy on the
full agent loop. `just eval` runs it; the results table is committed to the
README and quoted in the write-up. Eval traces reuse `traces.db` (D13).

**Why.** The project's thesis is *"I know RAG"*; unmeasured retrieval claims
are vibes. Concretely, D7's chunk constants and D8's rerank decision are
*defined* as eval outcomes — the harness isn't documentation, it's the
decision procedure. It also includes deliberately-hard questions (tables,
math — D6's known floor) so the write-up reports honest failure modes.

**Rejected.** *Ship demo first, evals later* (faster to a link; but then D7/D8
ship as guesses and the write-up's central claims are unbacked); *public
benchmark datasets* (BEIR etc. don't cover this corpus; a bespoke golden set
over our own corpus is both more honest and more impressive); *pure LLM-judge
without hand verification* (judge drift makes numbers unciteable).

**Risks accepted.** 50 questions is statistically thin — differences under
~5 points are noise and the write-up must say so. Hand verification is a
boring evening. Judge model cost is offline single-digit dollars.

**Revisit when.** Two configurations are within noise on a decision that
matters → grow the set until it discriminates.

---

## 4. Architecture

```
┌──────────────────────────── VPS (~$5-8/mo, 2vCPU/4GB) ────────────────────────────┐
│                                                                                    │
│  Caddy (TLS) ── static Next.js export                                              │
│      │                                                                             │
│      └─▶ FastAPI (uv)                                                              │
│            ├─ /api/explorer/*      SQL over corpus.db (read-only)                  │
│            ├─ /api/chat  (SSE)     agent loop (D1/D2)                              │
│            │     ├─ budget gate (D11)  ── traces.db (spend, sessions)              │
│            │     ├─ tools:                                                         │
│            │     │    search_corpus ─▶ chroma/ (HNSW) + corpus.db (FTS5) → RRF     │
│            │     │    query_metadata ─▶ corpus.db (read-only SQL)                  │
│            │     │    read_paper ─▶ corpus.db (chunk text by paper/page)           │
│            │     │    run_python ─▶ docker run --network none … (D10)              │
│            │     │    drive_ui ─▶ enum-validated event to frontend                 │
│            │     └─ Anthropic API (Haiku 4.5, prompt-cached)                       │
│            └─ /admin (basic-auth)  spend/trace dashboard                           │
│                                                                                    │
│  corpus.db  = papers + chunks + FTS5 (frozen snapshot, D12)                        │
│  chroma/    = embedded Chroma vector store, same chunk ids (D4)                    │
│  traces.db  = agent runs, tool calls, tokens, cost (D13)                           │
└────────────────────────────────────────────────────────────────────────────────────┘
   Cloudflare (DNS, rate-limit, bot filter) in front
   PDF bytes: browser ─▶ arxiv.org directly (D9); embeddings API for queries (D5)

Offline (Mac): pdfs/ ─▶ extract (D6) ─▶ chunk (D7) ─▶ embed (D5) ─▶ corpus.db + chroma/ + vectors.parquet
```

## 4b. Tech stack

One table per layer; **bold** items are the load-bearing choices already
argued in the decision records, the rest is the supporting cast this stack
implies. Anything not listed here is not in v1.

### Backend (Python, managed with `uv`)

| Piece | Choice | Role / note |
|---|---|---|
| Package/env | **uv** (`pyproject.toml`, locked) | replaces the venv+requirements.txt pattern of the collector; `uv run` in `just` recipes |
| API | **FastAPI** + uvicorn | routes, SSE via `sse-starlette`, OpenAPI schema doubles as the frontend's type source |
| Validation | pydantic v2 | request/response + tool-argument schemas (the `drive_ui` enum lives here) |
| LLM | `anthropic` SDK | Haiku 4.5, prompt caching, streaming (D3) |
| Embeddings | `openai` SDK | text-embedding-3-small @512d (D5) |
| Vector store | **chromadb** (embedded, pinned) | D4 |
| Metadata/FTS/traces | **sqlite3** stdlib + FTS5 | D4, D13; no ORM — the SQL *is* portfolio material |
| PDF extraction | **pymupdf4llm** | D6, offline only |
| Tokens | tiktoken / `anthropic.count_tokens` | chunk sizing + budget accounting |
| HTTP client | httpx | arXiv checks, health probes |
| Sandbox control | `docker` CLI via subprocess (or docker SDK) | D10; the invocation is ~20 lines, a library is optional |
| Lint/type/test | ruff, pyright, pytest | CI gate |

### Frontend (Next.js, managed with `pnpm`)

| Piece | Choice | Role / note |
|---|---|---|
| Framework | **Next.js** (App Router, `output: 'export'`) | static export served by Caddy (D13); TypeScript strict |
| Styling | **Tailwind CSS v4** | CSS-first config |
| Components | **shadcn/ui** (+ radix, lucide-react) | explorer chrome, panel, dialogs |
| Class utils | **cva + clsx + tailwind-merge** | come with the shadcn pattern; component variants |
| Server state | **TanStack Query** | explorer data fetching/caching against FastAPI |
| Client state | **zustand** | agent-panel session, timeline events, viewer state (`drive_ui` lands here) — one store, so TanStack owns server data and zustand owns UI/session state, never both |
| Animation | **motion** | timeline streaming-in, panel transitions |
| Tables/lists | TanStack Table + TanStack Virtual | 6,460-row explorer stays smooth |
| SSE client | `@microsoft/fetch-event-source` | POST + headers support that native `EventSource` lacks |
| Markdown | react-markdown + remark-gfm, **no raw HTML** | the §6 output-sanitization defense, as a dependency choice |
| API types | openapi-typescript (generated from FastAPI schema) | backend pydantic models become frontend types; no drift |
| PDF fallback | react-pdf/pdf.js — **only if** D9's iframe rung fails | do not install preemptively |
| Lint/test | eslint, prettier, vitest + Testing Library; Playwright smoke on the deployed demo flow | CI gate |

### Data & infra

| Piece | Choice | Role / note |
|---|---|---|
| Corpus artifacts | corpus.db + chroma/ + vectors.parquet | built by `just ingest`, versioned by snapshot date (D12) |
| Sandbox image | pinned python + pandas/numpy/matplotlib | pre-baked, no pip at runtime (D10) |
| Reverse proxy | Caddy | auto-TLS, static files, `/api` proxy |
| Orchestration | docker compose (api, caddy; sandbox containers spawned ad-hoc) | one `just deploy` |
| Edge | Cloudflare free tier (+ Turnstile if needed) | D11 |
| Backups | nightly copy of corpus.db/chroma/traces.db to object storage (rclone; litestream optional for traces.db) | D13 |
| CI | GitHub Actions: ruff+pyright+pytest, eslint+vitest, eval smoke subset | keeps D14 honest per PR |
| Task runner | just | already the repo's culture |
| Secrets | `.env` on the box only (Anthropic + OpenAI keys); never in the sandbox container | D10/D13 |
| Analytics | none in v1 (Caddy access logs suffice) | privacy + zero cost; revisit if traffic questions matter |

**Chat event flow.** User message → budget gate → agent loop streams SSE
events (`thinking`, `tool_call`, `tool_result_summary`, `ui_action`, `text`,
`cost`) → frontend renders timeline + answer + drives explorer. Every run
persists to `traces.db`.

## 5. Tool contracts (the security boundary is here)

All tools are **read-only by construction**, not by convention:

| Tool | Contract | Enforcement |
|---|---|---|
| `search_corpus(query, filters, k)` | hybrid top-k chunks + provenance | filters validated against schema enum |
| `query_metadata(sql)` | SELECT over `papers`/`chunks` views | SQLite opened read-only; single-statement SELECT-only parse; row + time limits |
| `read_paper(id, pages?)` | extracted text spans | id must exist in DB |
| `run_python(code)` | stdout + PNGs | D10 container: no net, ro-mounts, rlimits |
| `drive_ui(action)` | `open_paper\|goto_page\|set_filters` + validated args | server validates against enum + DB before forwarding; never free-form URLs/HTML |

Tool *results* re-entering the model are wrapped in fenced blocks labeled as
untrusted corpus content (see §6).

## 6. Threat model & hardening

**Assets:** the API-spend budget; service availability; visitors' browsers
(XSS); the box itself. Notably *not* data confidentiality — everything on the
box is public.

| Threat | Vector | Defense |
|---|---|---|
| Prompt injection | **PDF text is the injection surface** — malicious instructions inside papers enter via retrieved chunks | Chunks fenced + labeled untrusted in prompt; system prompt establishes data-vs-instructions; **capability side**: all tools read-only, sandbox no-egress, `drive_ui` enum-only — an injected agent has nothing harmful to *do*, which is the real defense |
| Denial of wallet | Scripted long agentic conversations | Token budgets per message/session/IP + global daily cap → replay mode (D11); step cap per message |
| Output-side XSS | Model emits hostile markdown/HTML sourced from a paper | Render as sanitized markdown (no raw HTML); citations verified server-side against real chunk ids before display |
| Sandbox abuse | Injected/hostile code in `run_python` | D10: no network, read-only public data, rlimits, fresh container, non-root |
| Cross-user leakage | Session bleed, shared caches | Ephemeral sessions (TTL, server-side); no cross-user caches except the immutable corpus; per-execution sandboxes |
| SQL injection (ish) | `query_metadata` is *designed* to accept model SQL | Read-only connection + SELECT-only single-statement parse + limits; worst case = reading public data slowly, bounded by timeout |
| Box compromise | Standard VPS surface | Caddy auto-TLS, ssh keys only, fail2ban, unattended-upgrades, admin behind basic-auth + Cloudflare |

**Residual risks, stated:** kernel-level container escape (accepted — public
data only); IP-rotation past per-IP budgets (global cap backstops); arXiv
blocking embeds (fallback ladder in D9). The write-up publishes this table.

## 7. Cost model

| Item | One-time | Monthly |
|---|---|---|
| Embedding corpus (~80–100M tok @ 512d) | $2–13 | — |
| Golden-set drafting + judge (offline, strong model) | ~$5–10 | — |
| VPS (Hetzner CX22-class) | — | ~$5–8 |
| Domain | ~$10/yr | ~$1 |
| LLM (Haiku, capped $0.50/day) | — | ≤$15 |
| Query embeddings | — | <$1 |
| Cloudflare free tier | — | $0 |
| **Total** | **~$10–25** | **≤~$22 worst case; ~$8–12 typical** |

Worst case is bounded *by construction* (D11 global cap + flat-cost VPS), not
by hope. The running per-conversation cost badge in the UI doubles as the
budget system's public face.

## 8. Build order

Each milestone ends demoable; risk is front-loaded (retrieval quality and the
agent loop are the make-or-break; UI is work but not risk).

1. **Ingest** — extract → chunk → embed → `corpus.db` + `chroma/`
   (+ `vectors.parquet` archive), as `just` recipes with stats + skip-list
   reporting. *Exit: corpus queryable via SQLite and Chroma with shared chunk ids.*
2. **Retrieval + evals** — hybrid search + golden set + `just eval`; tune
   until numbers stabilize. *Exit: committed eval table justifying D7/D8 choices.*
3. **Agent loop (CLI)** — D2 loop + all tools except `run_python`, driven from
   a terminal REPL; budget accounting + `traces.db` from day one. *Exit:
   multi-hop question answered with verified citations in the terminal.*
4. **Web app** — explorer, split-view viewer (D9 ladder tested here), agent
   panel with SSE timeline + cost badge, `drive_ui`. *Exit: full demo locally.*
5. **Sandbox** — D10 container + `run_python` + chart rendering. *Exit: the
   venue-rigor trend plot demo works end-to-end.*
6. **Hardening + deploy** — budget layers, replay mode, sanitization pass,
   VPS + Caddy + Cloudflare, backups, admin page. *Exit: public URL, caps
   verified by attacking it ourselves.*
7. **Write-up** — architecture doc mirroring these decision records, eval
   results, threat model, "what I'd change at 10× scale." *Exit: the README
   is the portfolio piece.*

## 9. v2 candidates (explicitly not now)

- Table/equation extraction (marker/docling) + computation over paper contents (D6 trigger)
- Router: cheap classic-RAG path for single-hop questions (D1 trigger)
- Live corpus updates in prod → forces pgvector migration (D12 → D4 chain)
- BYO-API-key mode for power users (D11 trigger)
- gVisor sandbox hardening (D10 trigger — mandatory if any private data appears)

## 10. Assumptions to validate early

- arXiv allows iframe embedding of PDF URLs (test in milestone 4; ladder ready).
- PyMuPDF4LLM failure rate on this corpus is low single-digit % (measured in milestone 1 stats).
- Embedded Chroma query latency at ~100k×512d stays well under 100 ms on the VPS class chosen, and its memory footprint fits the 4 GB box alongside Docker (benchmark in milestone 2; pgvector is the named fallback).
- Haiku 4.5 tool-use is reliable enough for an 8-step loop (milestone 3 CLI phase exists to find out cheaply).
