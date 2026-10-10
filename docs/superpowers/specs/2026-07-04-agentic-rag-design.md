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

**Note (2026-07-06, #23).** The loop validates cheap-first: a config-only
`base_url` seam (`agent_api_base_url`) can route the same `anthropic` client
at a cheap OpenRouter model (`smoke_model`) for a live smoke before spending
on Haiku. Prod serving is unchanged — empty `agent_api_base_url` is direct
Anthropic/Haiku, this decision's arithmetic still holds. Full record:
DECISIONS.md 2026-07-06.

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

**Amendment (2026-07-05, #13 — owner directive).** Provider is **Voyage AI**,
not OpenAI: model `voyage-4-lite` at `output_dimension=512`, $0.02/Mtok list
price with a **200M free-token quota** (per docs.voyageai.com, measured
2026-07-05) — the full corpus (~80–100M tokens) fits inside the free quota,
so the one-time cost drops from $2–13 to ~$0. voyage-3.5-lite (the alternative
this record originally named) is the same price but, as a superseded model,
gets no free quota; voyage-4-lite is its current successor. The 512-dim
`vectors.parquet` contract and the outage posture (D8 degrades to FTS5-only)
are unchanged. Client is raw httpx against the single REST endpoint — the
`openai` SDK leaves §4b; corpus embeds send `input_type="document"`, query
embeds must send `input_type="query"`. Frugality is a constraint while on the
free tier: rate-limit-aware batching, Retry-After-honoring backoff, and a
no-network `--estimate` gate before any paid/full run. Extra revisit trigger:
Voyage free-tier terms change, or milestone-2 evals justify a paid model.

**Second amendment (2026-07-05, #13 — owner directive).** Default backend is
now **local**, not Voyage: the measured unpaid-tier throttle (3 RPM / 10K
TPM, previous amendment) made the one-time corpus embed an 8.6h paced job and
— the sharper problem — would cap query-time throughput in production too.
`config.py` gets `embedding_backend: Literal["local", "voyage"]` (default
`"local"`); Voyage stays fully wired behind the flag, unchanged, for a future
paid tier. Local default model: **nomic-ai/nomic-embed-text-v1.5** (137M
params) via `sentence-transformers`, pinned to HF revision
`e9b6763023c676ca8431644204f50c2b100d9aab`, `truncate_dim=512` — its model
card documents trained-in Matryoshka checkpoints (768d: 62.28 MTEB, 512d:
61.96, negligible loss) rather than untested truncation, and its MTEB suite
includes arXiv-domain retrieval/clustering tasks directly relevant to this
corpus. Chosen over stronger-retrieval alternatives (snowflake-arctic-embed-
m-v2.0, Qwen3-Embedding-0.6B, jina-embeddings-v3 — all 300M-600M params)
because **the same model serves query-time embedding inside the FastAPI
process on the production VPS** (#16) — CPU-only, no GPU — so parameter count
against that budget outweighs a few MTEB points; ingest-time speed doesn't
carry the same weight (Mac + MPS, one-time job). Uses Nomic's mandatory
asymmetric prefixes (`search_document: ` / `search_query: `) — both sides
read the same config knobs, or recall silently degrades. Full gate record
(sentence-transformers, torch) and the model-selection evidence: DECISIONS.md
2026-07-05. **Per-model artifact keying** (new invariant, this amendment):
every vectors parquet lives at `corpus/vectors/<model_slug>.parquet` (slug =
short model name + dims) with full provenance in the parquet file metadata
(model, revision, dims, backend, created_at); readers refuse a slug mismatch
instead of silently mixing two models' vectors. Downstream: #14 keys Chroma
collections by the same slug, #18 tags eval runs by it. Extra revisit
trigger: a paid embeddings tier enters the budget, #18 evals show a paid or
larger model retrieves meaningfully better on this corpus, or #16's measured
query-time CPU latency on the target VPS is unacceptable.

**Amendment (2026-09-18, owner directive).** The default backend is
**`perplexity/pplx-embed-v1-0.6b` at 512d via OpenRouter** (`embedding_backend
= "openrouter"`); the local nomic path and the parked Voyage path both remain
selectable. Two facts moved the decision. **Coverage:** 144 of the 811 papers
with chunks had no vectors at all, the foundations among them, so they were
retrievable by BM25 only — and closing that locally is 2.6 CPU hours at a
measured 0.66 chunks/s, with a full re-embed at 16.9. Through the API the
whole corpus took 679s and $0.0849, which removes CPU time as the reason the
indexed set stays small. **Retrieval:** on the 33,931 chunks both models
cover, with identical queries and cosine in both spaces, exact-chunk recall@10
went 0.718 → 0.837 and MRR@10 0.539 → 0.656 (n=667, ten to thirteen points on
every metric, top-10 overlap 3.5/10).

Two honest caveats on that number. The previous amendment's revisit trigger
named **#18's evals**, which do not exist yet; what fired it was a
**proxy** — one mid-chunk 30-word span per paper retrieving its own chunk —
whose query text appears verbatim in the target, and which scores the vector
leg alone rather than the hybrid the app serves. And the swap puts a network
call in the query path where a local model stood: measured 107 ms/query
against 264 ms locally, with D8's fail-soft boundary degrading to BM25-only on
a transport error (confirmed in practice). Per-model artifact keying is what
makes this reversible: the nomic collection stays in Chroma beside the new
one, so rollback is one env var.

New operational invariant: an API embedding backend is **paced, not just
retried**. Perplexity rate-limits upstream of OpenRouter, and the five 429s in
the bulk run all traced to a cold-start burst, so `ingest/token_bucket.py`
reserves tokens forward in time and banks nothing — an idle stretch earns no
credit for a later burst. Batch caps come from the provider's own errors (512
items, 120,000 tokens per request), not its docs, which state none.

**Revisit when (this amendment).** #17/#18 land and the hand-verified golden
set disagrees with the proxy above; or the query-path network dependency costs
more in latency or failed turns than the recall gain is worth; or a
same-model hosted option appears that would let vectors be topped up rather
than rebuilt.

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

**Amendment (2026-07-05, #12).** Chunk *count* is eval-gated, not a target:
strict per-section packing produces ~2x the original 80–120k planning
estimate (24% of chunks <200 tokens), accepted for the demo because the
revisit trigger above is recall@k, not a count. A `chunk_min_tokens` merge
knob exists in config, disabled by default (0 = no merge); the #19 eval sweep
decides whether merging the small-chunk tail helps recall before it is
enabled. See DECISIONS.md 2026-07-05.

---

### D8. Retrieval: hybrid (vector + BM25 + RRF), filters pushed down; rerank only if evals demand it

*Amended 2026-10-05: the reranking ceiling is measured (D14 amendment of that
date): hybrid recall@10 79%, recall@50 93%.*

**Amendment (2026-10-05, owner directive): a local cross-encoder, measured.**
The rerank stage is a local cross-encoder (`rerank_model`, pinned like the
embedding model; `askrag/retrieval/rerank.py`), not Voyage or an LLM
listwise pass: `sentence-transformers` is already a dependency, it costs $0,
and it reads the query and the passage together, which is the thing an
embedding cannot do. It reorders hybrid's top `eval_pool_k` (50) into the top
10. Measured on 93 questions (run `492b61d7e3a5`):

| | Recall@10 | nDCG@10 | Latency, build host |
|---|---|---|---|
| Hybrid | 79% | 0.58 | 0.24 s |
| + gte-reranker-modernbert-base (2025, 149M, whole chunks) | 87% | 0.71 | 153 s |
| + ms-marco-MiniLM-L6-v2 (2022, 22M, 512 tokens) | 72% | 0.55 | 9 s |

The current model takes 8 of the 14 points the pool allows; its gains are on
vocabulary_mismatch (64 to 82%) and multi_hop (55 to 70%). The older web-QA
model loses ground, most on tables and math. `rerank_enabled` stays False:
the build host, which also serves the site, needs about three seconds per
passage on CPU, so a live rerank needs either a hosted reranker or a GPU, and
that is the next decision, not this one.

**Amendment (2026-10-05, owner directive): a hosted reranker, priced per
query.** The rerank stage has two scorers behind `rerank_backend`: `openrouter`
(OpenRouter's /rerank, default `voyageai/rerank-3-lite`, $0.02 per million
tokens) and `local` (the cross-encoder above, kept for comparison). The
billed cost is the provider's own `usage.cost`, never a rate table. 429s and
5xx are retried with backoff (the provider's shared project hit its
tokens-per-minute limit on the third question). Every eval row now reports
mean cost per query from the providers' billed figures (embedding, rerank,
rewrite). Run `bf072fb0bfba`, 93 questions:

| | Recall@10 | nDCG@10 | MRR | p50 latency | Cost / query |
|---|---|---|---|---|---|
| Hybrid + Voyage rerank-3-lite | 90% | 0.79 | 0.77 | 0.74 s | $0.00066 |
| Hybrid + local gte-modernbert (run `492b61d7e3a5`) | 87% | 0.71 | 0.67 | 153 s | $0 |
| Hybrid | 79% | 0.58 | 0.52 | 0.22 s | <$0.000001 |

Hosted reranking takes 11 of the 14 points the top-50 pool allows, gaining
most on vocabulary_mismatch (64 to 89%) and multi_hop (55 to 70%), for about
half a second and a tenth of a cent per search. `rerank_enabled` stays False
until the agent's answers are measured with it; a turn of about five searches
would add about $0.003 to a $0.0067 turn.

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

**Decision.** The viewer loads the **version-pinned** URL
`arxiv.org/pdf/<id><version>` (e.g. `…/pdf/2404.04643v2`, from the `version`
column) in an iframe, using `#page=N` fragments for citation jumps. Pinning
eliminates version skew *by construction*: the rendered PDF is byte-identical
to what we extracted, so page anchors and quotes can never silently drift
when authors revise. **Validated 2026-07-04**: pinned URLs serve 200/pdf
with no redirects, superseded old versions remain permanently retrievable,
and withdrawn papers still serve PDFs at pinned URLs (no stub/404 to handle).
99.5% of corpus rows have a version; the 31 NULL rows fall back to the
unpinned URL until backfilled from the Kaggle snapshot's `versions` array
during ingest (D18 — local, no network).
Alongside it, a **cited-excerpts pane** (our extraction, display-capped per
§6c — not a full-text mirror) shows the chunks the agent cited with
highlights and page anchors. The 11.6 GB corpus never deploys; prod ships
only the index artifacts — `corpus.db` + `chroma/`, ~1–2 GB total with text
and vectors (full text stays server-side for the model; §6c governs what
reaches the UI).

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

**Risks accepted.** arXiv may someday set `X-Frame-Options`/CSP that blocks
iframes (none today, verified), or rate-limit hot traffic. **Fallback
ladder, designed-in:** iframe → **PDF.js fetching the bytes directly from
arxiv.org in the user's browser** (verified permitted: `Access-Control-
Allow-Origin: *` + `Accept-Ranges: bytes`; no server proxy — arXiv's API
terms prohibit serving e-prints from our servers, so the earlier
caching-proxy idea is dead, see §6b) → extracted-text-only view with an
"open on arXiv" button. The split view keeps our text pane primary so the
demo survives any rung. `#page=N` precision varies by browser viewer —
citations also always show section + our text anchor, so page-jump is
enhancement, not correctness. **Observed 2026-07-04:** embedded webviews
without a native PDF plugin (Electron-style preview panes) turn iframe PDF
loads into downloads — rung 2 handles these; milestone 4 decides
per-browser rung selection (possibly PDF.js-by-default with the iframe as
the enhancement, inverting the ladder).

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
The budget gate (#21) is a pre-flight read, so concurrent in-flight requests
can overshoot the cap by at most (in-flight count) × (one turn's cost).
Amended 2026-10-10 (DECISIONS.md): the in-flight count is now fixed, at most
`chat_max_concurrent_turns` live turns per process (a full house answers 503),
and one turn's cost is bounded by the step cap, a per-step tool-call cap and a
per-call timeout. A turn that fails midway records the calls it already paid
for. The per-IP key is the visitor's address as our own proxies report it in
X-Forwarded-For, never the proxy's.

**Revisit when.** Real traffic regularly exhausts the cap (a good problem:
raise it, or add opt-in BYO-key for power users). Abuse defeats Cloudflare
free tier → Turnstile everywhere.

---

### D12. Frozen corpus snapshot in prod; the update pipeline stays offline

**Decision.** Prod serves a build-stamped snapshot (`corpus 2026-07`,
shown in the footer). The OAI-based `update` recipe is retired under D18
(no code path may touch export.arxiv.org); refreshing prod = re-run ingest
→ upload new SQLite file → restart.

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

**Amendment (2026-08-27, landing page).** The snapshot is now defined as *the
papers this month's page points at* (D16's amendment: `select_frontier.py`'s
manifest), refreshed on a monthly manual cadence — pull the month, extract
text, recompute citations, derive the frontier, chunk and embed it, rebuild.
**No VPS cron; D12's rejection of one stands unchanged**, and there is still
no serve-time freshness. What the amendment buys is that "stale" now has a
size: the page's own window banner states the id-months it covers, derived
from the citing side of the graph rather than written down anywhere.

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

**Amendment 2026-08-11 (owner directive, issue #81): the stack lands on the
tailnet before it lands in public.** The same `deploy/` artifacts run in two
ingress modes. *Tailnet (now):* Caddy publishes on `127.0.0.1` only and the
host's `tailscaled` fronts it via `tailscale serve` — tailnet HTTPS and a
MagicDNS name, no public DNS, no Cloudflare, no auth to build, no bill to
cap. *Public (#37):* the same compose file plus a Caddy site block with a
real hostname and auto-TLS. Three constraints surfaced building it, each
load-bearing:

- **Chroma cannot run from the read-only snapshot.** `PersistentClient`
  writes to its own SQLite on open (measured: `attempt to write a readonly
  database`), so the vector index is copied into a container-private volume
  at first deploy while the host snapshot stays untouched. corpus.db keeps
  its `mode=ro` posture unchanged (D4).
- **Prod torch is CPU-only.** PyPI's linux torch drags 2.9 GB of CUDA
  wheels into a box that will never have a GPU; linux resolves from
  PyTorch's CPU index instead (image 5.5 GB → 2.5 GB). macOS/MPS dev is
  untouched.
- **PDFs stay absent from the deployment, not merely unserved** — `pdfs/` is
  not mounted into any container and `.dockerignore` keeps `corpus/` out of
  every build context, so §6b holds by construction rather than by routing.

**Revisit when.** The demo goes public (#37 flips the ingress), or a second
deployment target appears (then the two modes want separate compose
overlays, not one file with an env switch).

**Amendment 2026-10-10 (owner directive): the site can go public without
the agent.** One deploy setting, `ASKRAG_AGENT_ENABLED` (off unless `true`),
refuses `POST /api/chat` with a 404 before a model client is built, and the
same value is baked into the web build to hide the agent's controls. The
server's refusal is the guarantee, the hidden UI is presentation. Every 200
GET under `/api` carries `Cache-Control` (`api_cache_control`), so an edge
cache in front of the public ingress serves the snapshot-derived reads
instead of the 4-core box.

**Amendment 2026-10-10 (owner directive): the public ingress is a
Cloudflare tunnel, not a Caddy site block.** A `tunnel` service in the same
compose file runs `cloudflared` with a remotely-managed tunnel token and
reaches `web:8080` over the compose network; Cloudflare terminates TLS for
`rag.nabin.org`. The box opens no inbound port and Caddy keeps
`auto_https off`. The token in `deploy/.env` is the switch (compose profile
`public`), so a tailnet-only deploy needs none. Caddy trusts the compose
subnet for `X-Forwarded-For`, matching the API's
`ASKRAG_TRUSTED_PROXY_CIDRS`, so the per-IP budget (D11) still keys on the
address Cloudflare saw. Rejected: Caddy auto-TLS (ports 80/443 open to the
internet on a box that runs other services); `cloudflared` as a host
service in front of the loopback port (host configuration outside the
repo, and the other services on this host already run it as a compose
sidecar).

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

**Amendment (2026-07-09, #17).** Field practice for *agentic* RAG (surveyed
July 2026) reshapes the harness into three layers plus dataset-as-code, and
settles the online/offline question for our scale:

- **Golden set is dataset-as-code, not a frozen file.** `evals/golden.jsonl`
  — the eval harness lives in a **root `evals/` uv-workspace package** (sibling
  to `backend`/`collector`, importing `askrag`, never the reverse; workspace
  prefactor #79) — one record per line, line-diffable and append-friendly
  (supersedes the `askrag/evals/golden_set.yaml` framing) — carrying `{id,
  question, type, expected_paper_id, expected_chunk_ids, expected_passage,
  difficulty, notes, verified}`. It lives in VCS so edits are code-reviewed and a
  score drop attributes cleanly to model vs rubric vs set change. It is NOT
  append-only/frozen: cases retire and labels get corrected as failure modes
  surface (the "static launch set is a benchmark, not a regression suite"
  anti-pattern).
- **What counts as a good pair (the dataset's quality bar).** Every record must
  be: *grounded* (answered by a specific chunk of a specific indexed paper, not
  general knowledge); *retrieval-requiring* (the base model can't answer it from
  parametric memory — checked, not assumed); *unambiguous* (which chunk(s) answer
  it is stable and knowable); *realistically phrased* (a researcher's question,
  not a paraphrase of the chunk — paraphrases test lexical overlap, not
  retrieval); *discriminating* (spans easy→hard so the set separates a good
  config from a bad one — an all-easy/all-impossible set gates nothing); and
  *representative* (stratified across categories/years). The four `type` buckets
  exist to stress our known failure axes: single-hop (baseline), multi-hop
  (composition), exact-match/acronym (the BM25 leg + keyword recall), known-hard
  table/math (D6's honest floor, included on purpose). Drafting + verification
  procedure is #17; the harness that consumes the set is #18 (retrieval) + the
  LLM-judged/trajectory issue.
- **Layer 3 — trajectory (new).** Retrieval is a tool the model calls (D1), so
  grade the *trajectory*, not just the answer: tool-call correctness (did it
  search before answering?), step efficiency vs `max_tool_steps_per_message`,
  wasted/looping calls, stop-reason sanity, latency + cost per answer. The data
  already exists in `traces.db` (D13) — no new capture. This is the most
  differentiated layer for a hand-built-agent-loop thesis, and per-step
  reliability compounds (a high per-step success rate still fails end-to-end
  across many steps), so measure it directly.
- **Citation accuracy is an explicit metric** in layer 2, not folded into
  "faithfulness": citation precision (does the cited paper/chunk actually
  support the claim?) + citation recall (is the answer fully covered by its
  citations?). Load-bearing for §6c cited answers. And faithfulness ≠
  correctness — a fully-grounded answer can still be wrong — so answer-
  correctness vs the golden `expected_*` is scored alongside faithfulness.
- **Online eval: out of scope, by design.** A live per-request scorer costs
  money against the ≤$22/mo cap with almost no traffic to score. The production-
  shaped substitute: the same offline harness runs over a *sample of real
  `traces.db` turns*, not only the golden set — on-demand replay, zero standing
  cost. Deliberately NOT built: live online-scoring service, drift crons,
  judge-prompt registry, continuous recalibration (all need traffic + budget we
  don't have).
- **Judge hygiene.** The judge model is a different (stronger) family than the
  agent model (Haiku) — never generator-as-own-judge. Report a one-time human-
  vs-judge agreement on a small labeled slice so the committed numbers are
  citeable; position/verbosity bias controls noted in the harness.

`just eval` still emits the committed README table; CI runs the free Layer-1
retrieval subset per PR (§10 CI), while the LLM-judged Layers 2–3 run on demand
/ at milestones for cost.

**Revisit when (amendment).** Real traffic grows enough that a sampled live
scorer would catch drift the on-demand traces-replay misses; or the judge-vs-
human slice shows weak agreement (rework the rubric before trusting numbers).

**Amendment (2026-09-30, owner directive): no human verification pass.** The
golden set is drafted by one model and checked by a model of another family,
and a record counts on the checks alone. `verified` leaves the record shape;
each record carries its `checks` instead. Issue #17's human pass and the
judge-vs-human agreement slice above are both dropped.

- **Drafter / checker.** GLM 5.3 Flash (Z.ai) drafts (`golden_draft_model`;
  replaced 2026-10-05, see that amendment);
  Muse Spark 1.3 contributor (Meta) checks (`golden_check_model`), both through
  OpenRouter, chosen by the owner: the account's guardrail blocks the
  Anthropic, Google and OpenAI slugs, and these two cost cents. A different
  family on the checking side is the whole defence against a model grading
  its own questions.
- **What a record must pass.** Deterministic: the `expected_passage` is a
  verbatim span of the named chunk and at most 50 words (§6c); an
  `exact_match` question contains its anchor term; any other question shares
  none of the chunk's rare terms, so it cannot be a BM25 gimme; an anchor term
  must recur in two papers, so a running header cannot become one. Checker:
  the passage alone answers the question, the question is about technical
  content rather than venue or authors, the drafted answer is right by the
  passage, and the question cannot be answered closed-book.
- **Ground truth is anchored twice.** `expected_chunk_ids` are the current
  `paper#seq` ids, which move whenever chunking constants do (#19); the
  verbatim passage is what survives that. The integrity test fails the moment
  a passage stops sitting inside its chunk, and a re-anchor pass fixes the
  ids from the passages.
- **Named in every number.** Results from this set are reported as
  model-checked, never as human-verified.

**Risks accepted.** Checker and drafter can share blind spots, so some records
will be wrong in ways neither model sees; uniqueness (no *other* chunk also
answers the question) is not checked, which understates recall where a
question has several answering chunks. Paper-level recall is reported beside
chunk-level recall for that reason.

**Revisit when (this amendment).** Two retrieval configurations land within
five points of each other on a decision that matters; or a spot check of
twenty records finds more than two wrong.

**Amendment (2026-10-01, owner directive): a vocabulary-mismatch type.** The
first retrieval run (#18) put BM25 at 97% recall@5 on single_hop: barring only
words in at most 40 chunks left questions sharing mid-frequency words with their
chunk, so the set could not show where semantic retrieval earns its place. A
fifth type, `vocabulary_mismatch`, holds the question a person types when they
have the problem a passage addresses but not the paper's terms. Its sources are
chunks that name a method, model or benchmark (the anchored pool, sampled after
every other type so no existing source moves). Its lexical rule bars every word
the chunk shares that sits in at most `golden_mismatch_max_shared_df` (500)
chunks, so everyday field words stay usable and the question still reads like a
person's. Because a drafter obeying that rule can write a question no one would
type, the checker also rules on `natural`: false for a stilted question or a
roundabout rewording of a term the asker would know ("malicious text that
hijacks a model" for prompt injection). The verdict is asked of this type only
and is `None` on the others. BM25's score on this type is held down by the
rule and is reported that way, never as a finding about BM25; the type
measures what the vector leg recovers when the searcher lacks the paper's
words, and whether fusion keeps it.

Measured on the first draft (60 candidates, 22 counted): recall@5 is BM25 36%,
vector 73%, hybrid 77%. Every BM25 hit came through field words the rule
allows on purpose ("regression", "channel", "diffusion"); tightening the bar
until those go would buy a lower BM25 number with questions nobody types.

**Revisit when (2026-10-01).** BM25 recall@5 on `vocabulary_mismatch` reaches
the vector leg's (the type stops separating them), or a spot check finds more
than two in ten counted questions unnatural.

**Amendment (2026-10-04, owner directive): questions are search queries.** The
set's questions averaged 35 words of scene-setting ("In the paper's transfer
learning setup, which optimizer...") that no one types into a paper search.
Every question is now at most `golden_question_max_words` (12) words, checked
deterministically, and the checker's `natural` verdict is asked of every type,
not only `vocabulary_mismatch`: false for a query that reads as written from the
paper (table numbers, "the authors", context only the paper supplies). Table
questions ask for the trend or comparison a table shows, not a cell. Short
table and two-passage queries cull hard (1 of 15 and 4 of 15 survived), so
their quotas rose to 45 and 35.

Measured (run `b4779b8e72ac`, 102 counted of 213, mean 9.6 words): recall@5 is
BM25 64%, vector 63%, hybrid 71%; on `vocabulary_mismatch` 48%, 52%, 62%. The
first amendment's 36%-vs-73% gap on that type came largely from question
length: a 35-word question carries enough paraphrase for the vector leg and
too many common words for BM25. On realistic queries neither leg wins alone and
fusion is what earns its place.

**Revisit when (2026-10-04).** A spot check finds counted queries that still
read as written from the paper, or a type falls under ten counted questions.

**Amendment (2026-10-05, owner directive): scored at the depth the agent
reads.** Retrieval evals scored recall@5 and @20 and fused each leg's top 20,
while the agent reads `search_top_k` (10) from a fusion of each leg's top 10:
the numbers described a configuration that does not ship. The runner now
scores at k = `search_top_k` only, retrieves each leg to that depth, and
reports recall@k, nDCG@k (binary relevance, as BEIR and MTEB report
retrieval), MRR within k, paper recall@k and median per-query latency;
`eval_recall_ks` is deleted. The README lists configurations ranked by
recall@k.

Measured (run `f0a35e4c5ab3`, 102 queries): recall@10 hybrid 80%, BM25 79%,
vector 73%; nDCG@10 0.59, 0.55, 0.51; median latency 218, 93 and 118 ms. The
95% bootstrap intervals on recall overlap for all three (hybrid 72-87%), so the
set ranks them but cannot separate them; growing it is the D14 revisit
trigger, not a reason to report the gaps as findings.

**Amendment (2026-10-05, owner directive): an ambiguity check, related
multi-hop pairs, and a new drafter.** A dry run of the agent against the set
found a counted question whose expected answer is wrong as typed: "how many
positive literals must a CNF clause contain", answered "one", which holds only
for Horn clauses. Short queries invite this.

- **Ambiguity check.** The checker also rules on `unambiguous`: false only when
  the expected answer would be wrong for the query as typed, because it holds
  for a special case the query does not name. A query answered by one paper's
  specific result stays in; an earlier wording that also culled those removed
  187 of 209. The committed set keeps its GLM-drafted questions and had this
  one verdict backfilled (one checker call per record, same wording), which
  culled 9 of 102; a record the checker never answered is culled, not passed.
  The set counts 93.
- **Related multi-hop pairs.** A pair is two body chunks of one paper (no
  abstract, introduction, conclusion or related work, which restate the whole
  paper) in different sections, sharing at least
  `golden_multi_hop_min_shared_terms` (3) rare terms. Random pairs gave
  unrelated facts that only a two-part question joins.
- **Drafter.** The account's guardrail dropped GLM 5.3 Flash. A full redraft
  counted 54 with gpt-oss-120b (paraphrased spans, questions about paper
  internals) and 83 with Space Bunny Alpha (stealth, free), against the GLM
  set's 93 after backfill; Space Bunny is the drafter for the next redraft.
  The drafter, the checker and the agent (`smoke_model`) are three different
  models, so no model writes or grades the test it takes.
- **Checkpointed redrafts.** Each checked record is appended to a progress
  file under a signature of models, prompts and caps; a killed run resumes,
  and a run with failed drafts keeps the file so a rerun retries only those.

**Amendment (2026-10-05, owner directive): the reranking ceiling and a
rewrite row.** Before building a reranker (D8) or crediting the agent's
query rewriting, the runner measures each in isolation. Every row also
reports recall at `eval_pool_k` (50), retrieved separately with each leg at
that depth: the most a reranker reordering that pool into the top 10 could
reach. A fourth row runs hybrid over one rewrite of the question by the
agent's own model (`just rewrites`, committed as `evals/rewrites.jsonl` so
`just eval` stays free of model calls; the runner refuses rewrites of
questions that have since changed).

Measured (run `b9a4726765fe`, 93 queries): hybrid recall@10 79% and
recall@50 93%, so a perfect reranker could add at most 14 points. One
rewrite then hybrid: recall@10 65%; it changed the outcome on 21 questions,
helping 3 and hurting 18, by generalising into field terms that match other
papers and by expanding acronyms wrongly. The set's questions are written
from their passages, which favours the original wording, so the row does not
show that rewriting hurts real searches; it shows that one rewrite replacing
the query is not the agent's advantage here.

**Amendment (2026-10-09, owner directive): the committed set carries no
passages.** The repo goes public, and 213 verbatim passages committed at once
quote some papers more than §6c lets one answer (up to five records and 134
words for one paper). The set is now two files from one list:
`corpus/evals/golden.jsonl` (gitignored) keeps every field, and
`evals/golden.jsonl` drops `expected_passage`. The drafter writes both; the
evals read only the committed one, since scoring needs the chunk ids alone.
The passage still re-anchors the ids after a chunking change, from the
drafted copy. Old commits of the set are rewritten to the same shape before
the repo is made public.

---

### D15. Operational telemetry: OpenTelemetry, JSON-first, built in from the start

**Decision.** `askrag/telemetry.py` is the single telemetry setup point,
initialized at every entrypoint from day one (ingest CLIs now, the FastAPI
lifespan when it exists). OpenTelemetry tracer + meter + logging
correlation; default export is structured JSON lines on stdout (zero cost,
greppable, journald/Caddy-friendly on the VPS). OTLP export sits behind a
config flag, off by default, so a collector (Jaeger in Docker, Grafana
Cloud free tier) can attach later with no code change. Ops telemetry stays
distinct from `traces.db`: traces.db is the product record (replays, evals,
timeline UI); OTel carries latency, errors, throughput, and token/cost span
attributes. Tracked as issue #43.

**Why.** Telemetry bolted on later means re-touching every tool, route, and
ingest stage; making it a from-the-start invariant (owner directive
2026-07-05) means every signal is machine-queryable from the first sample
run, within the ≤$22/mo budget (no APM vendor).

**Rejected.** *Paid APM/SaaS* (cost cap; ops data leaves our box);
*print-style logging* (unstructured, no trace correlation); *reusing
traces.db for ops signals* (conflates product data with ops and couples
their retention).

**Risks accepted.** Four more pinned deps and a little per-request
overhead — negligible at our QPS, measured in #43's acceptance. Stdout
JSON needs log rotation on the VPS (deploy issue's concern).

**Revisit when.** p95 overhead attributable to telemetry exceeds ~5 ms, or
debugging demands a live collector — set `otlp_endpoint` and attach one.

---

### D16. The API scopes to the indexed corpus; there is no `is_indexed` flag

**Decision.** The corpus the app serves = the papers with `chunks` rows
("indexed"), not the full `papers` table. `askrag.facets.INDEXED_PREDICATE`
(`EXISTS (SELECT 1 FROM chunks c WHERE c.paper_id = papers.arxiv_id)`) is
unconditionally part of `facets.where_clause`'s WHERE, so browse, `GET
/api/facets`, and `query_metadata`'s `count_papers` all scope to it for
free — one predicate, no per-consumer copy. `query_metadata`'s
`corpus_stats` applies the same `INDEXED_PREDICATE` directly to its own
`n_papers`/`year_min`/`year_max`/`n_categories` query, so the whole
`query_metadata` surface is uniformly scoped, not just `count_papers`.
`GET /api/papers/{id}` 404s a chunk-less paper. The frontend never sees a
non-indexed paper: no `is_indexed` field on the wire, no two-tier UI, no
badges. The agent's own `SYSTEM_PROMPT` (`askrag/agent/prompts.py`) names
no paper count either — it tells the model to call `corpus_stats` for the
real number instead of assuming or remembering one, so the model can't
contradict its own scoped tools by quoting a stale figure from its
instructions.

**Why.** `corpus.db` was seeded from a diverse ~200-paper sample; the full
6,460-paper ingest (#15) is still pending and human-gated. Before this
decision, browse returned all 6,460 `papers` rows while search/read/
excerpts only ever covered the ~200 with chunks — two universes diverging
silently, surfaced in the M4 live demo (2026-07-09, issue #73).

**Alternatives rejected.** An `is_indexed` flag with a two-tier UI (the
frontend would still reason about papers it can never retrieve — the bug
this decision closes, not a variant of it); filtering only at the FastAPI
route layer instead of the shared SQL predicate (reopens the copy-paste
risk D-2/#27 closed by centralizing count queries in `askrag.facets`);
leaving `corpus_stats` unscoped as a fast-follow (an interim call, revised
during PR #74 review — see DECISIONS.md: it kept the M4-demo bug reachable
through agent answers, e.g. "how big is your corpus?" → "6,460 papers"
while `count_papers`' own buckets summed to ~200 in the same turn);
deferring the `SYSTEM_PROMPT` fix to a fast-follow too (also rejected —
three lines, and deferring would have shipped a still-live copy of the
same bug, unconditionally, needing no tool call to surface).

**Risks accepted.** `query_metadata`'s `count_papers` and `corpus_stats`
ops change behavior for the agent too (they share `count_scalar`/
`count_grouped`/`INDEXED_PREDICATE` with `GET /api/facets`) — intentional,
since the agent can only retrieve indexed papers via `search_corpus`/
`read_paper`. `paper_facets` and `drive_ui`'s `open_paper`/`set_filters`
checks are scoped too (tightened 2026-09-30, when the RAG demo view made
"the agent knows only the indexed papers" a stated product property): an id
or category with no indexed papers is refused as unknown. Before that,
`paper_facets` answered any catalog id, which let the agent read a title and
venue for a paper it could not search, and `open_paper` could put an unreadable
paper in front of the reader.

**Revisit when.** #15's full ingest runs: the predicate then matches ~all
6,460 papers and every total self-corrects with no code change — this was
designed to converge, not to be swapped out.

**Amendment (2026-08-27, landing page).** The RULE is unchanged; what changed
is why the scope is affordable and how counts relate to lists.

- The indexed set is no longer an arbitrary prefix of the corpus. It is
  *derived from the landing page's own claims*: `ingest/select_frontier.py`
  emits the top-N cited works plus a capped, newest-first sample of each
  one's citers, and exactly those papers are chunked and embedded. Every link
  the page offers is therefore answerable **by construction** — a stronger
  property than "most of the corpus is indexed", and the reason the scope is
  no longer a bug being tolerated.
- `routes_landing.py` counts over `citations` WITHOUT `INDEXED_PREDICATE`,
  and this is deliberate: **a count of citations is not an offer of
  retrieval.** 1,174 papers really do cite Qwen3 whether or not we hold their
  text. What D16 forbids is the app surfacing a paper it cannot retrieve, so
  every LIST those routes return is restricted to indexed papers while the
  COUNTS stay honest totals. The page reads "8 of 1,174" and all 8 open. No
  `readable` flag reaches the wire, no two-tier UI, no badges — unchanged.
- `cited_works` is a separate table from `papers` for the same reason: a
  `papers` row means "we hold this text and can retrieve it", a `cited_works`
  row means "the Kaggle catalog describes it". Merging them would let a work
  nothing can read surface wherever a readable paper can.

**Amendment (2026-09-13, home-as-dashboard; superseded 2026-10-02, see §4c
decision 2: Explore is `/`, the dashboard is `/citations`).** The front door keeps its
composition and gains two sections, both fed by `routes_landing.py` under the
same rule: `GET /api/coverage` (per id-month holdings — counts, so honest
totals with no indexed restriction) and `GET /api/latest` (newest papers — a
list, so `INDEXED_PREDICATE`-restricted; fresh but unindexed papers appear on
their own once the index run covers them). No new route: the dashboard IS `/`,
which is why the amendment lives here and not in §4c.

**Amendment (2026-09-15, count-vs-claim rule).** The count-vs-list rule above
governs what the API may OFFER. It says nothing about what the page may
CLAIM, and the page overclaimed: "we pulled every cs paper arXiv posted in
the window", where the window was `min/max(citing id-month)` and the real
coverage was 94% of July 2026, 49% of August, 5% of September. So the rule
gains a second half: **every count is a count of what we hold, and any
sentence that turns one into a claim about the literature carries the
catalog's own denominator beside it.** `catalog_months` (from
`ingest/kaggle_seed.count_cs_papers_by_id_month`) is that denominator;
`papers.has_text` is the parse rate's; the "window" becomes a cohort derived
by a stated rule (`landing_cohort_min_share`). A denominator the snapshot
cannot supply is reported as unknown, never borrowed. See DECISIONS.md
2026-09-15.

**Amendment (2026-09-16, the census panels).** With July and August 2026
collected to 99.95% and 99.99% of the catalog, two panels may describe arXiv
rather than the corpus, which no earlier panel was allowed to do:
`GET /api/census/categories` (primary-category share per month) and
`GET /api/census/uptake` (work from one month already cited by the next).
Both are gated on `landing_census_min_coverage` (0.9), and a cohort month
below it is returned in `excluded` and named on the page rather than dropped:
a month missing from a chart of the field's output reads as a month the field
went quiet, when what stopped was our collecting. September 2026 is that
month today — the mirror's folder for it stops at 2609.04203. The
count-vs-list rule is untouched: these are counts, and a row opens the same
foundation detail whose citer list stays indexed-only.

**Amendment (2026-09-16, the catalog route).** This one relaxes the rule, and
says exactly where. `GET /api/catalog/papers` (route `/papers`) lists the WHOLE
`papers` table, indexed or not, and each row carries an `indexed` boolean on
the wire — the field the original decision refused.

What made the refusal right was that the app had one promise, retrieval, and
a two-tier UI would have let a reader reason about papers it could never
serve. The catalog page makes a different and smaller promise: what arXiv
posted and what we hold of it. That promise is true of all 65,503 rows, and
it is the only surface where the 64,692 unreadable ones stop being a number
on the dashboard and become papers a reader can reach. So:

- The scope widens and the affordance narrows TOGETHER. An indexed row opens
  the reader; every other row opens arxiv.org, version-pinned (§6b). The
  boolean exists to route the row, not to rank it, and there is no badge, no
  second tier of styling, no "upgrade" path.
- **The agent's surface is untouched.** `facets.INDEXED_PREDICATE` still
  scopes browse, `GET /api/facets`, `GET /api/papers`, `GET /api/papers/{id}`
  and every `query_metadata` op. `routes_catalog.py` builds its own WHERE and
  never calls `facets.where_clause`, so nothing the model can reach widened.
- Nothing on this path loads a model. The filter is SQL over `papers` plus
  BM25 over `papers_fts` (title + abstract), a new external-content FTS5 table
  in `_write_corpus_db`. Titles and abstracts come from the Kaggle snapshot
  and exist for every row, which is why this surface can cover the table when
  retrieval cannot. §6c is unaffected: no chunk text is read here.

This is the "found" versus "readable" distinction the revisit trigger below
anticipated, arriving one tier early and only for human-facing lists. The tool
contracts still do not have to make it. See DECISIONS.md 2026-09-16.

**Revisit when.** A breadth tier lands (abstract-level index over all cs
history). A paper matched at abstract level *cannot be quoted* — we hold no
text for it — so the tool contracts would then have to distinguish "found"
from "readable", which this decision currently does not have to.

---

### D17. Withdrawn (2026-10-02, owner directive): PDFs are kept

D17 made PDFs transient: fetch, extract, delete, keep only text and citation
edges. It was never implemented, and the owner withdrew it on 2026-10-02.
PDFs fetched from the GCS mirror stay under `corpus/pdfs/`. D19 depends on
that, since card images render from the PDFs we hold, and keeping them means a
chunker or extractor change re-runs over local bytes instead of a download
pass. §6b is unchanged: holding a PDF for internal processing is not serving,
proxying or caching it to anyone, and no PDF leaves our infrastructure.

The cost is disk, about 4 MB per paper (a month of cs is about 50 GB), and the
volume, not transfer, is now what bounds how many months we hold. The number
stays so that D18 and later keep theirs.

---

### D18. No code path touches export.arxiv.org; versions backfill from the seed

**Decision (2026-09-13).** Ingest reads only the Kaggle snapshot (ids +
metadata) and the GCS mirror (PDF bytes). Three former `export.arxiv.org`
consumers are gone: the OAI-PMH harvest, the arXiv PDF scraper (including the
GCS-miss fallback), and the index build's version-backfill query. NULL-version
rows backfill from the snapshot's own `versions` array instead — same pinning,
no network. The `update`/`oai-*` collector recipes are dead with them; monthly
freshness is a manual Kaggle snapshot + GCS-mirror pull (the D12 amendment's
cadence, unchanged).

**Why.** A routine index rebuild was 429/503-gated by a single 31-id metadata
query — arXiv throttles the whole IP, and one throttled host should never hold
a local build hostage. The scraper lanes were already vestigial (every pull
since August has been seed + GCS), and the OAI lane's one unique value,
incremental freshness, is not worth a second network master: the snapshot
lands monthly and the mirror syncs weekly, which covers the page's monthly
cadence with room to spare.

**Alternatives rejected.** *Keep OAI for metadata only* (preserves incremental
pulls, but keeps the throttle dependency alive for the smallest gain — the
monthly snapshot already carries the same fields); *retry/backoff on the
backfill query* (treats the symptom; the next throttle lands mid-build
again); *leave NULL versions unpinned* (weakens D9's pinning guarantee for 31
rows to save a seed pass that costs seconds via early-exit).

**Revisit when.** The Kaggle snapshot stops shipping (then freshness needs a
new source anyway), or arXiv publishes a bulk metadata endpoint with stated
limits — a documented allowance is a different fact from today's best-effort
tolerance.

### D19. A card image for every paper, rendered on demand and cached as a file

**Decision (2026-09-16).** `/papers` shows a small crop of each paper beside
its title. `ingest/render_thumbnails.py` renders it from the PDF we already
hold: the first image placed large enough on a page to be a figure rather
than a logo, else the top half of page one. Output is a 320px JPEG at
`corpus/thumbs/{arxiv_id}.jpg`.

**The cache is the file, and there is nothing else.** No manifest, no
`papers.thumbnail` column, no field on the wire. Caddy serves
`/thumbs/{id}.jpg` off disk and falls through to `GET /api/thumb/{id}` on a
miss; that route renders the crop, writes it into the same tree, and returns
the bytes, so every later request is a static file again. `just thumbnails`
warms the backlog in bulk and is an optimisation, never a prerequisite. The
property this buys: a new month of papers shows pictures the moment its PDFs
land — no reindex, no batch run standing between the data and the page.

**Nothing fetches arxiv.org to build a card.** Thirty cards would be thirty
requests per render, and from arXiv's side that is a scraper. The image comes
from our own PDF, every time. See CLAUDE.md's hard constraints.

**The licence governs the card, not the file.**

| Licence | Papers | What the card owes |
|---|---|---|
| arXiv `nonexclusive-distrib` | 36,560 | A link back to arxiv.org for the paper itself. No notice: the crop is fair use, not a grant. |
| CC BY, BY-SA | 22,956 | Attribution (title, authors, source link) plus the licence named and linked. |
| CC BY-NC-SA, BY-NC-ND | 5,233 | The same, and askRAG must stay non-commercial. |
| CC0 / public domain | 551 | Nothing. |

The card already carried title, authors and a version-pinned link to
arxiv.org; the licence notice is what this decision adds
(`lib/license-label.ts`, `catalog-results.tsx`). **We never host the PDF
download** — that part of §6b rule 3 is unchanged and is the line that
actually matters.

**Why fair use covers the default-licence majority.** A low-resolution crop
shown beside a link back to the source is the indexing use *Kelly v. Arriba
Soft* (9th Cir. 2003) and *Perfect 10 v. Amazon.com* (9th Cir. 2007) both
held to be fair: transformative, low-resolution, serving reference rather
than consumption. `thumbnail_width` is therefore a compliance setting as much
as a layout one — raising it toward a readable page is the change that breaks
the argument.

**Alternatives rejected.** *Render in the reader's browser from arxiv.org*
(needs no licence reasoning, but is exactly the fan-out the hard constraint
forbids); *gate the file on the licence* (the first version of this decision:
images for the 26,253 CC papers and a grey glyph for the other 39,250, which
read §6b's reasoning past what it protects and made a worse column than the
question is hard); *a manifest plus a `papers.thumbnail` column* (also tried:
it made a card image wait on a corpus rebuild, which is the coupling the
on-demand path exists to remove); *a generated placeholder for every paper*
(a coloured square per category is the glyph we already have, with more
bytes); *ship no images* (65,503 rows of text, and a figure is the fastest
thing a reader judges a paper by).

**Consequence, and it is the sharpest one here.** The api container now
mounts `pdfs/` read-only, where its ABSENCE used to be the guarantee that no
serving path could reach an e-print. That guarantee moves from the mount to
the code: `routes_thumbnails.py` is the only reader, it validates the id
against a literal arXiv-id pattern before building a path, and it returns a
rendered JPEG and never the source. `test_routes_thumbnails.py` asserts both.
The web container mounts the thumbnail cache read-only and nothing else.
**askRAG carrying ads, a paid tier, or an enterprise plan would put the 5,233
NC papers out of licence**, which is a product constraint no code path can
check.

**Revisit when.** askRAG stops being non-commercial (then the NC rows' crops
come down before anything ships), arXiv states a position on derived images
(a documented allowance or refusal replaces this reading), or a rightsholder
objects to a specific paper (§6b's takedown path already covers it, and
deleting one JPEG is the whole remedy).

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
| Package/env | **uv** (`pyproject.toml`, locked) | repo-wide convention, collector included since #9; `uv run` in `just` recipes |
| Telemetry | **opentelemetry-sdk** + otlp-http exporter + fastapi/httpx instrumentation (pinned) | ops signals from day one; JSON stdout default, OTLP env-gated (D15) |
| API | **FastAPI** + uvicorn | routes, SSE via `sse-starlette`, OpenAPI schema doubles as the frontend's type source |
| Validation | pydantic v2 | request/response + tool-argument schemas (the `drive_ui` enum lives here) |
| LLM | `anthropic` SDK | Haiku 4.5, prompt caching, streaming (D3) |
| Embeddings | **sentence-transformers** (local, default) / httpx → Voyage REST API (parked) | nomic-embed-text-v1.5 @512d, `embedding_backend` flag (D5 second amendment); Voyage (voyage-4-lite @512d) stays wired behind the flag |
| Vector archive | **pyarrow** (pinned) | writes/reads per-model `corpus/vectors/<model_slug>.parquet` — the D4/D5 embedding archive index layers rebuild from; gate record in DECISIONS.md 2026-07-05 |
| Vector store | **chromadb** (embedded, pinned) | D4 |
| Metadata/FTS/traces | **sqlite3** stdlib + FTS5 | D4, D13; no ORM — the SQL *is* portfolio material |
| PDF extraction | **pymupdf4llm** | D6, offline only |
| Tokens | tiktoken / `anthropic.count_tokens` | chunk sizing + budget accounting |
| HTTP client | httpx | arXiv checks, health probes |
| Sandbox control | `docker` CLI via subprocess (or docker SDK) | D10; the invocation is ~20 lines, a library is optional |
| Lint/type/test | ruff, **ty**, pytest | CI gate — Astral trio (uv+ruff+ty), one vendor; entry point `just check` |

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
| Theming | **next-themes** | light/dark/system with the choice persisted; sets `.dark` before first paint, which a static export cannot do itself (#85) |
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
| CI | GitHub Actions runs `just check` (ruff+ty+pytest; frontend lint+types once scaffolded; eval smoke subset) | keeps D14 honest per PR; local gate == CI gate |
| Task runner | just | already the repo's culture |
| Secrets | `.env` on the box only (Anthropic + OpenAI keys); never in the sandbox container | D10/D13 |
| Analytics | none in v1 (Caddy access logs suffice) | privacy + zero cost; revisit if traffic questions matter |

## 4c. Repository layout

The whole tree, root to leaf. Naming rules first, because they are the point:

- **A file's name states what it does.** There is no `core.py`, `utils.py`,
  `helpers.py`, `service.py`, `manager.py`, or `misc/` anywhere in this tree.
  The single tolerated exception is frontend `lib/utils.ts`, which contains
  exactly the shadcn `cn()` helper and nothing else, because fighting that
  convention costs more than it buys.
- **One boundary per file.** Each file has one responsibility, sized to be
  readable in one context-window pass (soft target: under ~400 lines; a file
  growing past that is a design smell, not a formatting problem).
- **One name per concept, everywhere.** `paper`, `chunk`, `trace`, `budget`,
  `session`, `replay`, `facet` mean the same thing in SQL, Python, SSE event
  names, TypeScript types, and zustand stores. `grep -r budget` finds every
  piece of budget logic in the repo; that property is maintained on purpose.
- **Tests mirror source names.** `budgets.py` ↔ `test_budgets.py`. An agent
  (or human) finding one immediately knows the path to the other.

Three layout decisions resolved here, deliberately:

1. **The existing collector moves to `collector/`** and its data artifacts to
   `corpus/` (gitignored). The collector is Part 0 of the pipeline and stays
   runnable; milestone 1 includes this move (`git mv`, paths updated, its
   README section adjusted). Root stays clean: three top-level codebases
   (`collector/`, `backend/`, `frontend/`), one data directory, one deploy
   directory, docs.
2. **No dynamic routes in the frontend.** *(Amended 2026-08-27: no DYNAMIC
   routes — a second STATIC route is compatible and now exists. The landing
   page is `/`, the app shell moved unchanged to `/app`. Both are prerendered
   by the export; neither needs `generateStaticParams`. The rule was always
   about not SSG-ing 6,460 pages, not about page count. Amended again
   2026-09-30: the routes are `/` (overview), `/papers` (the whole catalog)
   and `/demo` (the indexed papers with the reader and the agent), all
   static. `/app` is gone: its list and filter rail were a second list
   implementation over the same papers, and the demo reuses the catalog's.
   The open paper is `/demo?paper=<id>&page=<n>`; viewer-store owns only
   those two keys, and the list's filter in the same URL is owned by the
   catalog, so the agent's `set_filters` writes the URL rather than the
   store. Amended again 2026-10-02: Explore is the home page. The routes
   are `/` (the whole catalog, filtered), `/citations` (the counted
   overview, renamed) and `/demo`. `/papers` is gone with no redirect: the
   site is tailnet-only and pre-launch. The share of each cohort month we
   hold moved from the citations hero to Explore's top bar, and
   `/api/coverage` names the cohort's months so the client never re-derives
   `landing_cohort_min_share`. Same day: `/trends` holds the category census
   (the one count over what arXiv posted rather than what we hold), and the
   "just indexed" list and its `GET /api/latest` are deleted, since Explore
   sorted newest already lists the same papers. Amended again 2026-10-06:
   `/benchmarks` shows the retrieval eval. It is the one route that reads no
   API: `evals/publish_results.py` (`just eval-publish`) writes the committed run's scores to
   `frontend/lib/benchmarks/retrieval.json` and the page imports it, because
   the numbers change only when an eval run is committed. Titles and section
   names only, never passage text (§6c).)* Static export (D13) plus 6,460
   papers makes `paper/[id]/page.tsx` the wrong tool (it would SSG 6,460
   pages or fight `generateStaticParams`). The app is one shell; the open
   paper is a search param (`/?paper=2606.12345&page=4`), owned by the
   viewer store and synced to the URL so views are shareable/back-button
   friendly. This is also what makes `drive_ui` trivial: the agent mutates
   the same store the URL reflects.
3. **Replays live in `traces.db`.** A showcase replay is just a recorded
   trace flagged `showcase=1` — no separate format, no second store, and the
   replay player exercises the same timeline UI code path as live SSE.

```
rags/
├── justfile                         # umbrella recipes: ingest, eval, dev, deploy — delegate into backend/frontend
├── README.md                        # the portfolio front door: pitch, architecture summary, eval table, links
├── .gitignore                       # corpus/, .env, node_modules, .venv, traces.db
├── .github/
│   └── workflows/ci.yml             # runs `just check`: ruff+ty+pytest; frontend lint+types; eval smoke subset (D14)
├── docs/
│   └── superpowers/
│       ├── specs/                   # this document and its predecessors
│       └── plans/                   # implementation plans (one per milestone)
├── collector/                       # Part 0 — existing arXiv corpus collector (moved in #9)
│   ├── pyproject.toml               # uv-managed, uv.lock committed
│   ├── justfile                     # collector recipes; root justfile delegates here
│   ├── arxiv_ingest.py              # discovery + download + arxiv.db index (already built)
│   ├── fetch_ids.py                 # download a NAMED id list (the frontier manifest), vs the discovery paths above
│   ├── test_arxiv_ingest.py
│   ├── test_diverse.py
│   └── README.md                    # collector usage (formerly the root README)
├── corpus/                          # gitignored data; every artifact `just ingest` reads or writes
│   ├── pdfs/{YYYY}/{MM}/*.pdf       # 11.6 GB source PDFs (local only, never deployed — D9)
│   ├── arxiv.db                     # collector's metadata index (input to ingest)
│   ├── archive.zip                  # Kaggle metadata seed (~1.7 GB) the collector reads ids from
│   ├── data/                        # collector caches: facet pickles, internal-citations.json
│   ├── extracted/{arxiv_id}.json    # per-paper extraction cache: markdown, sections, page map (D6)
│   ├── corpus.db                    # papers + chunks + FTS5 — the deployable index (D4)
│   ├── chroma/                      # embedded Chroma store, same chunk ids (D4)
│   ├── vectors/<model_slug>.parquet # embedding archive, one file per model+dims (D5 2nd amendment); parquet metadata carries model/revision/dims/backend/created_at
│   ├── models/                      # local backend HF weights cache, gitignored, never committed (D5 2nd amendment)
│   └── skiplist.json                # papers extraction failed on, with reasons (D6)
├── backend/
│   ├── pyproject.toml               # uv-managed; deps pinned, chromadb version pinned (D4)
│   ├── uv.lock
│   ├── askrag/
│   │   ├── config.py                # ALL tunables + env in one pydantic-settings class: paths, model ids, chunk sizes, budget caps, RRF k
│   │   ├── telemetry.py             # single OTel setup: tracer/meter/log correlation; JSON stdout default, OTLP env-gated (D15)
│   │   ├── db.py                    # read-only SQLite connection factories for corpus.db; read-write for traces.db
│   │   ├── traces.py                # trace record schema + writer/reader; feeds timeline UI, evals, admin, replays
│   │   ├── api/
│   │   │   ├── app.py               # FastAPI assembly: routers, CORS, lifespan (opens stores once), static admin
│   │   │   ├── routes_explorer.py   # GET /api/papers, /api/papers/{id}, /api/facets — browse/filter/search
│   │   │   ├── routes_catalog.py    # GET /api/catalog/papers, /api/catalog/facets — the whole papers table, filtered (D16 amendment 2026-09-16)
│   │   │   ├── routes_landing.py    # GET /api/landing, /api/foundations/{id}, /api/coverage — the citation graph Citations ranks (D16 amendment)
│   │   │   ├── routes_census.py     # GET /api/census/categories, /api/census/uptake — what arXiv posted, for months held above `landing_census_min_coverage`
│   │   │   ├── routes_chat.py       # POST /api/chat — budget gate → agent loop → SSE stream; replay mode when capped
│   │   │   ├── routes_admin.py      # GET /admin — basic-auth spend/trace dashboard (D13)
│   │   │   └── sse_events.py        # the SSE event vocabulary: thinking|tool_call|tool_result_summary|ui_action|text|cost|done — single source, mirrored by frontend lib/sse.ts
│   │   ├── agent/
│   │   │   ├── loop.py              # THE hand-built loop (D1/D2): messages, tool dispatch, step cap, stop conditions
│   │   │   ├── context_window.py    # eviction/summarization of stale tool results; keeps loop under token ceiling
│   │   │   ├── budgets.py           # D11 layered caps: per-message, per-session, per-IP, global daily; reads/writes traces.db
│   │   │   ├── prompts.py           # system prompt + the untrusted-content fence for tool results (§6)
│   │   │   └── replay.py            # streams a showcase=1 trace back through the same SSE vocabulary
│   │   ├── tools/
│   │   │   ├── registry.py          # tool JSON schemas sent to the model + name→handler dispatch table
│   │   │   ├── search_corpus.py     # tool: hybrid retrieval with filters → chunks + provenance
│   │   │   ├── query_metadata.py    # tool: enum'd count/histogram/point-lookup ops; no model SQL (§5)
│   │   │   ├── read_paper.py        # tool: extracted text spans by paper id + page range
│   │   │   ├── run_python.py        # tool: dispatch code to sandbox/runner, collect stdout + PNGs
│   │   │   └── drive_ui.py          # tool: enum-validated UI actions, server-verified against corpus.db (§5)
│   │   ├── retrieval/
│   │   │   ├── hybrid_search.py     # vector + BM25 → reciprocal rank fusion → top-k (D8); rerank behind a flag
│   │   │   ├── vector_store.py      # Chroma wrapper — THE pgvector seam (D4 revisit lands here)
│   │   │   ├── fts.py               # FTS5/BM25 query construction and escaping
│   │   │   └── embeddings.py        # embedding API client, one function for corpus batch + query single (D5)
│   │   ├── ingest/
│   │   │   ├── kaggle_seed.py       # streaming reader for corpus/archive.zip — one member name; targeted lookups + the per-month cs census
│   │   │   ├── extract_text.py      # pdfs/ → corpus/text/{YYMM}/*.txt (PyMuPDF page text); `--months` scopes a top-up
│   │   │   ├── extract_citations.py # corpus/text/**/*.txt → citations.tsv (the landing page's every number)
│   │   │   ├── resolve_cited_works.py # citations.tsv + archive.zip → cited_works.jsonl (works we cite but do not hold)
│   │   │   ├── select_frontier.py   # THE MANIFEST: citations.tsv → frontier.json; also `--verify` (D16 amendment)
│   │   │   ├── extract_pdfs.py      # pdfs/ → corpus/extracted/*.json + skiplist.json (PyMuPDF4LLM, D6); `--frontier` scopes to the manifest
│   │   │   ├── chunk_papers.py      # extracted/ → section-aware ~1k-token page-anchored chunks (D7)
│   │   │   ├── embed_chunks.py      # chunks → vectors/<model_slug>.parquet, local (default) or Voyage backend, batched, resumable (D5)
│   │   │   ├── render_thumbnails.py # pdfs/ → thumbs/{id}.jpg, on demand or in bulk (D19)
│   │   │   ├── build_indexes.py     # chunks + vectors → corpus.db (FTS5) + chroma/, shared chunk ids (D4)
│   │   │   └── ingest_stats.py      # per-stage report: counts, sizes, skip reasons, snapshot datestamp (D12)
│   │   ├── sandbox/
│   │   │   ├── runner.py            # docker run --network none, ro-mounts, rlimits, tmpfs, PNG collection (D10)
│   │   │   └── image/
│   │   │       └── Dockerfile       # pinned python + pandas/numpy/matplotlib; no pip at runtime
│   │   └── evals/
│   │       ├── golden_set.yaml      # ~50 hand-verified question → expected paper/passage pairs (D14)
│   │       ├── run_retrieval_evals.py  # recall@k, MRR per retrieval config; emits the README table
│   │       ├── run_answer_evals.py  # end-to-end agent runs judged for faithfulness + citation accuracy
│   │       └── judge_prompts.py     # LLM-judge rubrics (strong model, offline — D3)
│   └── tests/                       # mirrors askrag/ module names, one test file per source file
│       ├── test_loop.py             # loop against a scripted fake model: tool dispatch, step cap, stop
│       ├── test_context_window.py
│       ├── test_budgets.py          # every cap layer trips at its boundary; replay mode engages
│       ├── test_registry.py         # tool schemas validate; unknown tool names rejected
│       ├── test_query_metadata.py   # per-op correctness; off-enum group_by + free-form sql field refused
│       ├── test_drive_ui.py         # enum validation; nonexistent paper ids refused
│       ├── test_hybrid_search.py    # RRF math; filters push down; empty-leg degradation (D5 outage mode)
│       ├── test_chunk_papers.py     # section boundaries respected; page anchors correct; overlap size
│       ├── test_runner.py           # sandbox: no network, ro-mounts, timeout kill, PNG capture
│       └── test_sse_events.py       # event vocabulary serializes to what lib/sse.ts expects
├── frontend/
│   ├── package.json                 # pnpm; scripts: dev, build (static export), lint, test, gen:api
│   ├── pnpm-lock.yaml
│   ├── next.config.ts               # output: 'export' (D13); /api proxy rewrite for dev only
│   ├── tsconfig.json                # strict
│   ├── app/                         # Next.js App Router — one shell, no dynamic routes (decision 2 above)
│   │   ├── layout.tsx               # root layout: fonts, theme, providers (TanStack QueryClient)
│   │   ├── page.tsx                 # THE LANDING PAGE: counted citations, no input box in the critical path
│   │   ├── app/page.tsx             # the app: explorer + viewer + agent panel composition
│   │   └── globals.css              # Tailwind v4 entry + design tokens
│   ├── components/
│   │   ├── landing/
│   │   │   ├── hero-stats.tsx       # the four counted facts + the cohort and its catalog share, derived from the graph
│   │   │   ├── foundations-table.tsx # the ranking that survives a rerun — counts, no clustering
│   │   │   ├── foundation-detail.tsx # the evidence: co-cited works + the INDEXED citers ("8 of 1,174", D16)
│   │   │   ├── methods-note.tsx     # how the numbers are made, and what they are not
│   │   │   └── holdings-chart.tsx   # how much of each month we hold, against the catalog's own count (D16 amendment 2026-09-15)
│   │   ├── explorer/
│   │   │   ├── paper-table.tsx      # TanStack Table + Virtual over /api/papers; row click → viewer store
│   │   │   ├── facet-filters.tsx    # category/year/facet controls; writes viewer store filter state
│   │   │   └── corpus-search-bar.tsx # semantic + keyword search box hitting /api/papers?q=
│   │   ├── viewer/
│   │   │   ├── paper-split-view.tsx # layout: pdf frame | cited excerpts; reads viewer store
│   │   │   ├── arxiv-pdf-frame.tsx  # D9 rung 1: version-pinned arxiv.org iframe with #page=N; detects embed failure → ladder
│   │   │   └── cited-excerpts-pane.tsx # cited chunks only, display-capped per §6c; section nav + "PDF page N" anchors
│   │   ├── agent-panel/
│   │   │   ├── chat-panel.tsx       # message list + input; wires use-agent-stream to session store
│   │   │   ├── tool-timeline.tsx    # live tool-call timeline rendered from SSE events (motion)
│   │   │   ├── cost-badge.tsx       # running token/$ per conversation, from cost events
│   │   │   ├── message-markdown.tsx # react-markdown + remark-gfm, raw HTML disabled (§6), verified-citation chips
│   │   │   └── replay-banner.tsx    # "live budget spent — watching a recorded session" mode switch
│   │   ├── shell/
│   │   │   ├── drawer-panel.tsx     # docked column at/above a breakpoint, slide-over drawer below (#83); one element, one child instance
│   │   │   ├── app-bar.tsx          # narrow-viewport bar: filters hamburger + agent toggle; hidden from lg:
│   │   │   └── theme-menu.tsx       # light/dark/system icon button + menu, mounted in the footer (#85)
│   │   └── ui/                      # shadcn-generated primitives, unmodified (regenerate, don't edit)
│   ├── lib/
│   │   ├── api-client.ts            # typed fetch wrapper over generated types; single base-URL owner
│   │   ├── api-types.gen.ts         # openapi-typescript output — GENERATED, never hand-edited
│   │   ├── sse.ts                   # fetch-event-source wrapper; discriminated union mirroring sse_events.py
│   │   ├── breakpoints.ts           # the md/lg thresholds JS needs, paired with the Tailwind classes (#83)
│   │   ├── arxiv-links.ts           # the ONE place arxiv.org URLs are built — version-pinned (D9/§6b)
│   │   └── utils.ts                 # cn() only (see naming rules)
│   ├── stores/
│   │   ├── agent-session-store.ts   # zustand: messages, timeline events, budget/replay state
│   │   ├── ui-shell-store.ts        # zustand: which narrow-viewport overlay is open (#83); deliberately NOT URL-synced
│   │   └── viewer-store.ts          # zustand: open paper, page, filters — drive_ui's target, synced to URL search params
│   ├── hooks/
│   │   ├── use-papers-query.ts      # TanStack Query hooks for explorer endpoints
│   │   ├── use-media-query.ts       # docked-or-drawer, for the ARIA half of the layout (#83)
│   │   └── use-agent-stream.ts      # POST /api/chat via lib/sse.ts → dispatches events into stores
│   └── tests/
│       ├── tool-timeline.test.tsx   # events render in order; unknown event types don't crash
│       ├── message-markdown.test.tsx # raw HTML is stripped; citation chips only for verified ids
│       └── viewer-store.test.ts     # drive_ui actions mutate store + URL symmetrically
├── deploy/
│   ├── compose.yml                  # api + caddy services; corpus artifacts mounted ro; sandbox spawned ad-hoc (not a service)
│   ├── Dockerfile.api               # uv workspace build, non-root, CPU-only torch; corpus mounts, never bakes
│   ├── Dockerfile.web               # pnpm static export baked into Caddy; no Node process in prod
│   ├── Caddyfile                    # TLS, static frontend, /api reverse proxy (SSE flush), /admin basic-auth
│   ├── .env.example                 # every secret/setting the box needs, documented, no values
│   ├── README.md                    # deploy + tailnet runbook (D13 amendment)
│   └── backup.sh                    # nightly rclone of corpus.db, chroma/, traces.db (D13)
└── e2e/
    └── demo-flow.spec.ts            # Playwright smoke: load explorer → ask agent → citation opens viewer (against deployed URL)
```

## 4d. Engineering principles — classic rules, agent-era calibration

The classics still hold; what changed is the *cost model* they were priced
against. Code is now cheap to write and cheaper to regenerate, but every
line still costs the same to read, and most readers of this codebase will be
agents navigating by grep and file names. Each rule below states the classic
form, what we actually practice, and why.

**KISS → "boring is a feature."** Practice: step on the standard pattern
(Next.js conventions, FastAPI idioms, shadcn's generated structure) unless a
decision record says otherwise. Cleverness that saves ten lines but breaks
the "an agent can predict where things live" property is a net loss. Every
deviation from convention in this repo has a number (D1–D14) — if a future
deviation doesn't earn a decision record, it doesn't happen.

**YAGNI → still ruthless, with named exceptions.** Practice: no speculative
generality — except the seams a decision record's *revisit trigger*
explicitly names (e.g. `vector_store.py` exists so the pgvector migration is
a file swap, `arxiv-pdf-frame.tsx` isolates the D9 fallback ladder). A seam
without a written trigger is speculation; delete it. This is YAGNI upgraded
from a taste rule to a bookkeeping rule: "gonna need it" claims must be
written down or they don't count.

**DRY → deduplicate *knowledge*, tolerate duplicated *mechanics*.** The
classic rule-of-three ("refactor on the third copy") is genuinely debatable
now: generating a third copy costs nothing, and a wrong abstraction costs an
agent far more navigation than repetition does — so we bias *later* than
rule-of-three for code shape. But knowledge — constants, schemas, event
vocabularies, prompts — must live in exactly one place, because divergent
copies are the bug class agents introduce most easily. Concretely:
`config.py` owns every tunable; `sse_events.py` owns the event vocabulary
and `lib/sse.ts` mirrors it under test (`test_sse_events.py`); pydantic
models own API shapes and `api-types.gen.ts` is generated, never edited. Two
route handlers that look similar stay similar-looking until a *knowledge*
change (not an aesthetic itch) forces them together.

**Single responsibility → one boundary per file, sized for a context
window.** Practice: the tree above is the enforcement — file names are
contracts, and a file that needs "and" to describe is two files. Soft cap
~400 lines. This is the classic rule with a new justification: a file an
agent can hold in one read gets edited correctly; a 2,000-line module gets
edited by patch-and-pray.

**Explicit over implicit (grep-first).** No metaprogramming, no dynamic
imports, no convention-magic dispatch beyond what the frameworks impose. The
tool registry is a literal dict, not a decorator scan. Agents debug by
reading and grepping, not by stepping through a debugger — code whose
behavior is visible in its text is code agents maintain safely. Same rule
for names: one concept, one name, everywhere (§4c).

**Contracts at boundaries, checked by machines.** pydantic at every API and
tool edge, TypeScript strict, generated types across the language gap, and
tests that pin the cross-language mirrors. The type checker is the first
reviewer of every agent-written diff; the more of the spec that lives in
types, the less that lives in vibes.

**Tests are the executable spec.** TDD where the behavior is designable
up-front (budgets, chunking, tool contracts — the `tests/` list in §4c *is*
the acceptance criteria); test-after is acceptable for exploratory UI work,
but the security-relevant behaviors (§6 table) are never test-after. A test
file mirrors its source file so the spec for any module is one `ls` away.

**Comments state constraints, not narration.** A comment exists only to say
what the code cannot: "read-only by construction, see D4," "this mirror is
tested by test_sse_events.py — change both." Narration comments rot and
mislead the next agent; constraint comments are load-bearing.

**Known-unknowns are written, unknown-unknowns get seams.** Everything this
spec couldn't resolve is in §10 with a validation milestone; the honest
admission is that some things are only knowable by building (Haiku's loop
reliability, arXiv's embed behavior). The response isn't more upfront
design — it's putting those bets behind small files with tested contracts,
so being wrong is a file swap, not a rewrite.

**Chat event flow.** User message → budget gate → agent loop streams SSE
events (`thinking`, `tool_call`, `tool_result_summary`, `ui_action`, `text`,
`cost`) → frontend renders timeline + answer + drives explorer. Every run
persists to `traces.db`.

## 5. Tool contracts (the security boundary is here)

All tools are **read-only by construction**, not by convention:

| Tool | Contract | Enforcement |
|---|---|---|
| `search_corpus(query, filters, k)` | hybrid top-k chunks + provenance | filters validated against schema enum |
| `query_metadata(op)` | enum'd structured metadata queries — `count_papers` (scalar/histogram), `paper_facets` (point lookup), `corpus_stats` (totals); no model-authored SQL | discriminated union of exactly 3 typed ops (mirrors `drive_ui`); every op runs a fixed parameterized SQL template, `group_by` resolves through a server-side column map, never string-interpolated |
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
| SQL injection (ish) | N/A — no model-authored SQL; `query_metadata` is an enum'd union of parameterized shapes only (DECISIONS.md 2026-07-06, pre-#23) | Vector retired: filters bind as `?`, `group_by` resolves through a server-side column map, no free-form SQL field exists in the schema |
| Box compromise | Standard VPS surface | Caddy auto-TLS, ssh keys only, fail2ban, unattended-upgrades, admin behind basic-auth + Cloudflare |

**Residual risks, stated:** kernel-level container escape (accepted — public
data only); IP-rotation past per-IP budgets (global cap backstops); arXiv
blocking embeds (fallback ladder in D9). The write-up publishes this table.

## 6b. arXiv policy compliance (primary sources read 2026-07-04)

Researched from arXiv's API Terms of Use, brand guidelines, bulk-data pages,
and license pages. These are adopted constraints, not optional:

1. **Name.** No "arXiv" in the project name or anything implying official
   connection (brand guidelines prohibit names that "imply or tend to imply
   some official connection"). *askRAG* is clean. Never suggest endorsement.
2. **Attribution, verbatim, in the site footer** (`layout.tsx`): *"Thank you
   to arXiv for use of its open access interoperability. This service was
   not reviewed or approved by, nor does it necessarily express or reflect
   the policies or opinions of, arXiv."* Logo: skip it (use is allowed only
   for acknowledgement and tightly constrained — the sentence suffices).
3. **Never serve e-prints from our servers.** Explicitly prohibited by the
   API ToU. PDFs reach users only via their own browser fetching arxiv.org
   (iframe rung 1, PDF.js direct cross-origin fetch rung 2 — CORS-verified).
   This is also why D9's old caching-proxy fallback was deleted.
4. **Directing users to arXiv is the *encouraged* pattern** — the API ToU
   says so explicitly, and policy is silent on iframes specifically. Link
   the abstract page (`arxiv.org/abs/<id>`) alongside the embedded PDF;
   bulk-data terms require linking back to arXiv for downloads from any
   full-text-based tool.
5. **Metadata is CC0 1.0 — abstracts included by name** (API ToU footnote
   lists "title, abstract, authors, identifiers, and classification terms").
   The explorer can store, display, and index all of it freely.
6. **Full text is NOT CC0.** Most papers grant arXiv only a non-exclusive
   distribution license; arXiv "cannot grant others the right to distribute."
   Storing and processing full text for retrieval falls under the ToU's
   "retrieve, store, and use… for research purposes" allowance; exposing
   bulk full text for download does not. Display posture (summaries,
   snippet limits) is specified in §6c.
7. **Ingest-side rate limits** (visitors' organic PDF traffic has no stated
    limit — "interactive use by human users" is arXiv's stated first
    priority): moot since D18 — no code path requests anything from
    export.arxiv.org, so there is nothing left to pace. (Historical note: the
    legacy API/OAI allowance was ≤ 1 request per 3 s single-connection.)
8. **Courtesy:** arXiv asks to be told when products launch — do that at
   deploy (milestone 6 checklist).

## 6c. Content display posture (what users may see of paper text)

Resolved from the content-license research (primary sources + operating
precedent: Semantic Scholar TLDRs, Emergent Mind, alphaXiv, HF Papers —
all display generated summaries + links, none rehost default-license full
text). Risk management, not legal advice; each rule tagged by its basis.

| Rule | Basis |
|---|---|
| Server-side extraction, embedding, and LLM analysis over locally stored PDFs; the model may read full text via `read_paper` | Explicitly anticipated by policy — arXiv's bulk-data program exists for this; its blog names "semantic search interfaces" as an intended use |
| Titles, abstracts, authors, categories displayed freely in the explorer | Explicitly permitted (CC0) |
| LLM-generated summaries/answers in our own words, cited (paper id, section, page), labeled AI-generated | Established precedent; policy silent |
| Verbatim quotes: **≤50 words per quote, ≤3 quotes per paper per answer**, always quotation-marked + cited; raw retrieved chunks are never dumped to the UI; no sequential-excerpt browsing that could reconstruct a section | Conservative choice where policy is silent |
| **No full-text pane for default-license papers.** The reading surface is the arXiv-served PDF (D9); our pane shows cited excerpts + navigation anchors only | Follows from the no-serving rule — displaying full extracted text is redistribution re-typeset |
| Per-paper `license` field carried from the Kaggle seed into `corpus.db` at ingest; CC0/CC-BY papers *may* show fuller text with attribution (v2 option, not v1 scope); the "vast majority" default-license papers get the caps above | Conservative choice; the metadata provides the field for exactly this |
| Takedown path: a contact link, and removal of a paper's summaries/excerpts from the index on author objection | Conservative choice mirroring Semantic Scholar et al. |

**Clarification (2026-08-28, DECISIONS.md; issue #36):** row 4 caps quotes at
50 words and 3 per paper, but never said what COUNTS as a quote, and the floor
decides whether the rule is usable. It is `config.quote_min_words` (15): a
verbatim run shorter than that is shared terminology, not an excerpt. Measured
on a live turn — at a 6-word floor a faithful Qwen3 answer tripped the 3-quote
limit nine times on phrases like "increasing the proportion of STEM, coding,
reasoning", and the remediation shredded the paragraph. Row 4's stated targets
are substantial verbatim quotes and sequential-excerpt section reconstruction;
neither is reachable in runs that short, so enforcing there costs faithfulness
and buys no protection. Enforcement lives in `askrag/api/answer_guard.py`, and
over-budget or over-length runs are elided with "[…]" rather than a policy
sentence, so the surviving prose still reads.

**Clarification (2026-07-06, DECISIONS.md; issue #58):** row 1 and row 4 are
two different enforcement points, not one. `read_paper` (row 1) is the
MODEL's read tool — it returns page-bounded extracted text up to
`config.read_paper_max_tokens`, a real budget for a real deep read, and must
never re-apply row 4's ≤50-word/≤3-quote cap. Row 4 governs verbatim quotes
surfacing in an ANSWER shown to a user; it is enforced at answer-assembly
(#23/#30) and the frontend (#26), server-side, per answer — never at the
model-read tool boundary. §6b (no PDF bytes served/cached/proxied) applies
identically to both and is unaffected by this split.

Design consequence, applied throughout this spec: the viewer's text pane is
`cited-excerpts-pane.tsx` — cited excerpts, not a full-text mirror. It renders the chunks
the agent actually cited (display-capped), section headings as navigation,
and "open in PDF → page N" anchors — the PDF iframe is the reading surface.
This costs little: the demo's trust moment is *citation lands on the real
page*, which survives intact.

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

**What a turn costs is the provider's number when the provider states one**
(amended 2026-08-11, issue #81). OpenRouter returns `usage.cost` — the exact
amount billed — on every response, and the Anthropic SDK preserves it as a
pydantic extra; `agent/pricing.py` uses it verbatim. The `agent_usd_per_mtok_*`
table in `config.py` remains the fallback and prices the prod path unchanged,
since real Anthropic reports no cost field (D3). A turn is priced entirely one
way or the other — a mixed sum would *under*-report, the one error direction
D11's caps cannot absorb. This matters because the two disagree by more than a
rounding error: the tailnet deployment's smoke model bills ~16x below the Haiku
rate table, so a table-priced ledger exhausted a day's cap in three questions
while real spend was under a cent.

## 8. Build order

Each milestone ends demoable; risk is front-loaded (retrieval quality and the
agent loop are the make-or-break; UI is work but not risk).

1. **Ingest** — first the §4c repo reorganization (collector → `collector/`,
   data → `corpus/`, backend scaffold), then extract → chunk → embed →
   `corpus.db` + `chroma/` (+ `vectors.parquet` archive), as `just` recipes
   with stats + skip-list reporting. Also: per-paper `license` field from
   the Kaggle seed into `corpus.db` (§6c) and version backfill for the 31
   unversioned rows (D9). *Exit: corpus queryable via SQLite and Chroma
   with shared chunk ids.*
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

- ~~arXiv allows iframe embedding of PDF URLs~~ **Validated 2026-07-04**
  (Playwright headless Chromium + header inspection, two ids old/new):
  `arxiv.org/pdf/<id>` sends **no X-Frame-Options and no CSP** — framing is
  unblocked; PDFs render inline in Chromium's viewer and `#page=N` fragments
  work (viewer opened at page 3/4). Bonus: `Access-Control-Allow-Origin: *`
  + `Accept-Ranges: bytes`, so the rung-2 PDF.js fallback is *also* CORS-
  permitted with ranged loading. Caveats carried forward: rendering was
  verified in new-headless/desktop Chromium — verify Safari/iOS in
  milestone 4; headers are arXiv policy and could change (the D9 ladder
  stays in the design for that reason).
- PyMuPDF4LLM failure rate on this corpus is low single-digit % (measured in milestone 1 stats).
- Embedded Chroma query latency at ~100k×512d stays well under 100 ms on the VPS class chosen, and its memory footprint fits the 4 GB box alongside Docker (benchmark in milestone 2; pgvector is the named fallback).
- Haiku 4.5 tool-use is reliable enough for an 8-step loop (milestone 3 CLI phase exists to find out cheaply).
