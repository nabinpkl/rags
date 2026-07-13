# Coherence checkpoint — retrieval+tools slice (2026-07-06)

**Auditor:** Opus slice-boundary auditor (read-only). **Verdict:** `NEEDS-WORK`.
This is the first checkpoint; "Deltas" is a baseline note, not a diff.

## Slice audited

Issues #13/#14 (ingest: extract → chunk → embed → build_indexes), #16
(retrieval spine), #22 (§5 tool boundary). Files read as a whole:

- `ingest/embed_chunks.py`, `ingest/build_indexes.py`, `ingest/chunk_papers.py`
  (record shape), `ingest/extract_pdfs.py` (crash contract only).
- `retrieval/hybrid_search.py`, `retrieval/fts.py`, `retrieval/vector_store.py`,
  `retrieval/embeddings.py`.
- `tools/registry.py`, `tools/search_corpus.py`, `tools/read_paper.py`,
  `tools/query_metadata.py`, `tools/drive_ui.py`.
- `config.py`, `db.py`. Cross-checked against spec §5, §6/§6b/§6c, D1, D5, D8,
  D10, D12 and `DECISIONS.md`.
- Confirmed green: `uv run pytest` → 229 passed, 1 skipped. Tests mirror source
  names 1:1 (§4d).

## Coherent (genuinely hangs together)

- **The per-model embedding keying spine is the strongest thing in the slice.**
  `config.embedding_model_slug` is the single source of truth, threaded without
  drift: `embed_chunks` writes the slug into both the parquet *path* and the
  parquet *file metadata* (`EmbeddingProvenance`); `read_vectors(expected_slug)`
  refuses a mismatched parquet; `build_indexes` names the Chroma collection by
  the same slug and re-checks via `read_vectors`; `vector_store` looks the
  collection up by that slug and raises if absent; the query path
  (`retrieval/embeddings.py`) reads the same slug. Two models' vectors cannot
  mix by construction. D5's core requirement holds end to end.
- **The asymmetric doc/query prefix pairing cannot drift**: ingest ("document")
  and retrieval ("query") both build their backend through the *one*
  `make_backend(settings, input_kind=…)` factory, reading the same
  `embedding_doc_prefix`/`embedding_query_prefix` knobs. The nomic recall trap
  (silent degradation if the query prefix is missed) is closed structurally.
- **Read-only-by-construction is real, not conventional.** Every tool opens
  corpus.db only via `db.connect_corpus` (`mode=ro` URI); the write path
  (traces.db) is a separate factory. `query_metadata` is defense-in-depth and
  correct: ro connection + single-statement (`Cursor.execute` refuses `;`) +
  PREPARE-time authorizer with a *named function allow-list* (closing the
  `randomblob`/`zeroblob` timeout-bypass from PR #57) + progress-handler
  deadline + fetch-`max_rows+1` cap. `fts.build_match_query` neutralizes all
  FTS5 operator syntax and strips control chars. `drive_ui` is enum-only and
  validates every target (paper/page/category) against corpus.db before return.
- **The two-leg filter contract agrees across layers.** `build_indexes` writes
  Chroma metadata keys `{category, year}`; `vector_store.query` filters on
  exactly those keys; `fts.search_bm25` filters `p.primary_category`/`p.year`;
  `Filters` carries `category/year_min/year_max` into both legs. RRF fusion is
  pure and hand-testable. Fail-soft is as documented: dead vector leg → BM25;
  dead corpus.db → fatal.
- **`config.py` tunables are actually read.** Spot-checked the retrieval/tools
  knobs (`rrf_k`, `search_top_k`, `search_corpus_max_k`, `rerank_enabled`,
  `quote_max_words`, `max_quotes_per_paper`, `query_metadata_*`) — each has a
  live reader. No set-but-unread or read-but-unset in this slice.

## Findings (ranked; most severe first)

### 1. MAJOR — `read_paper` caps the model to ~150 words/call, contradicting §6c row 1 and D1. **Gates #23.**
`tools/read_paper.py:96-97` applies the **answer/display** quote caps
(`quote_max_words=50`, `max_quotes_per_paper=3`) at the **model-facing tool**
boundary — a `read_paper` call returns at most 3 spans × 50 words ≈ 150 words,
and `tests/test_read_paper.py` asserts this as a hard invariant ("No
combination of page range + quote caps can reconstruct the paper").

This contradicts the spec:
- §6c **row 1**: "Server-side extraction, embedding, and LLM analysis … *the
  model may read full text via `read_paper`*." The ≤50w/≤3-quote limit is §6c
  **row 4**, whose basis is *verbatim quotes in answers* and "raw retrieved
  chunks are never dumped to the **UI**" — a display posture, not a model-read
  posture. The implementation collapsed the display cap onto the model's read
  tool.
- D1: the agent "decides when to … *read a specific paper deeper*." With a
  150-word ceiling, "deeper" is impossible — the agent cannot read a paper.

It is also **internally incoherent with `search_corpus`**, which hands the
model the *full* ~1000-token chunk text uncapped (`hybrid_search._hydrate`
selects `c.text` raw). So the model can already obtain full chunk text via
search, but the tool §6c names as its full-text path is the *most* restricted.
The cap on `read_paper` protects nothing §6c actually protects (UI display /
verbatim answer quotes) and only cripples the deep-read capability D1 is built
on.

**This is a finding against the DECISION, not the diff** (per auditor brief): §6c
rows 1 and 4 are in tension and the implementor resolved toward the restrictive
reading. Coordinator call needed: the ≤3-quotes-per-paper *answer/display* cap
belongs at answer-assembly / the frontend (#23/#30/#26), where §6c row 4 and the
per-answer composition gate (see Note A) live; `read_paper` should give the
model substantial page-bounded text (a token budget, not a 150-word wall).
Resolve **before #23** designs its read/answer strategy, or #23 encodes a hollow
deep-read and reworks later.

### 2. MAJOR — no uniform tool-result type or fence/serialize seam; #23 hits this immediately. **Gates #23.**
`registry.dispatch()` returns `Any` over four *heterogeneous* shapes:
`SearchCorpusResult`, `ReadPaperResult`, `QueryMetadataResult` (frozen
dataclasses, one nesting a `tuple[ScoredChunk, …]`) and a `drive_ui` action
(a pydantic model, unwrapped from `RootModel`). §5 requires tool results
re-entering the model to be "wrapped in fenced blocks labeled as untrusted
corpus content" (§6) — that serialization + fencing layer does not exist yet,
and no shared method does it (`grep` finds no `to_model`/`model_dump`/`asdict`
seam in `tools/` or `agent/`; `agent/` holds only `budgets.py`).

Because the return types mix dataclass and pydantic, #23 cannot fence with one
`model_dump()`; it must build a per-type adapter. Name it now so #23 designs the
untrusted-fence layer deliberately: either give every handler a uniform
`.to_model_payload() -> dict` (or return pydantic models across the board) so
#23 fences once, or accept an explicit per-type switch in the loop. Either way
this is a contract #23 consumes on day one.

### 3. MINOR — vector leg catches bare `except Exception`, degrading to BM25 on *any* error. Non-gating.
`hybrid_search.py:149` swallows every exception into the D8 fail-soft path. D8
sanctions degradation on vector *outage* (model gone, parked-API down); a bare
`except Exception` also converts a *logic bug* in the embed/query path
(KeyError, AttributeError, dim mismatch) into a permanent silent BM25-only mode,
surfaced only as a WARNING log + `askrag.degraded` span attr — no test or alert
fails. This is the classic fail-soft-masks-bug hazard and contradicts the
python-backend rule "catch narrowly." Narrow to the operational error set
(`VectorStoreError`, `httpx`/IO/model-load errors) so a code bug fails loud.

### 4. MINOR — D8's "facet" filters are recorded but only partly implemented. Non-gating.
D8: filters are "category, year, **facets** — pushed into Chroma's `where` and
SQL." Only `category`/`year` are wired: `Filters` carries three fields, and
Chroma metadata (`build_indexes._load_chroma`) carries only `{paper_id,
category, year}`. The other collector facets present in `papers`
(`venue_rigor`, `authority`, `niche_idf`, `author_novelty`, `revisions`) are
not filterable, and adding them to the vector leg later needs a **Chroma
rebuild** (metadata is baked at index time). Flagged so this is a conscious
deferral, not silent drift — if #23 or the explorer UI expects facet filtering,
it is absent today.

## Notes (carried, not findings)

- **Note A — per-answer §6c composition gate** (two `read_paper` calls, or
  repeated `search_corpus`, exceeding ≤3 quotes/paper *within one answer*) is
  known and owned by #23/#30 per the task; not re-litigated. It interacts with
  Finding 1: if `read_paper` stops enforcing the quote cap, the per-answer cap
  *must* land in #23/#30/frontend, not vanish.
- **Note B — registry omits `run_python`.** `registry.py` advertises itself as
  "the entire tool surface," but §5's fifth tool (`run_python`, D10 sandbox) is
  absent — it lands with #33 (needs Docker). Expected staging; flagged so #23's
  loop is built for 4 tools now and an added 5th later, not surprised by the gap.

## Deltas from last checkpoint

Baseline — first checkpoint, no prior to diff. Recorded state: keying spine and
read-only construction coherent; the tool→agent-loop boundary (Findings 1–2) is
the unfinished edge #23 inherits.

## Verdict

`NEEDS-WORK`. Findings 1 and 2 gate #23. Finding 1 is a coordinator decision
(a §6c amendment: where the model-read vs answer-display cap belongs) that must
resolve before #23 designs how the agent reads and quotes. Finding 2 is a small
pre-#23 contract (uniform, fenceable tool-result shape) #23 consumes
immediately. Findings 3–4 are minor and do not gate the next slice. The
retrieval/ingest core beneath the tool boundary is coherent and may stand as-is.
