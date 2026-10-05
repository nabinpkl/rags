"""Every tunable and all environment access in ONE pydantic-settings class.

House rule (spec §4c/§4d, issue #10 acceptance): this is the only module that
reads the environment — `os.environ` / `os.getenv` must appear nowhere else in
askrag. Enforced by tests/test_config.py, which scans the source tree.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/askrag/config.py -> repo root. Data artifacts live in the repo-level
# corpus/ directory (spec §4c); prod layouts override via ASKRAG_* env vars.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASKRAG_", env_file=".env", extra="ignore")

    # --- paths (spec §4c) -------------------------------------------------
    corpus_dir: Path = _REPO_ROOT / "corpus"
    # traces.db is the backend's ONLY writable store (D13): spend, sessions,
    # traces, replays. Everything under corpus_dir is read-only in serving.
    traces_db_path: Path = _REPO_ROOT / "traces.db"

    # --- model ids + pricing (D3, D5) -------------------------------------
    agent_model: str = "claude-haiku-4-5-20251001"
    # Pricing feeds budget accounting and the UI cost badge (D3, §7); update
    # alongside any model change or the caps below lie.
    agent_usd_per_mtok_in: float = 1.00
    agent_usd_per_mtok_out: float = 5.00
    agent_usd_per_mtok_cache_read: float = 0.10
    # --- eval harness model ids (D14 amendment; issue #79 prefactor) -------
    # Golden set (D14 amendment 2026-09-30): no human pass, so the drafter and
    # the checker are different models, and neither is `smoke_model`, the
    # agent the set measures — the checker is the only thing standing between
    # a model and its own questions. OpenRouter slugs, called through
    # OpenRouter's Anthropic-compatible endpoint; all three are on the
    # account's guardrail allowlist (probed 2026-10-05). The drafter is a
    # stealth model, free and temporary: fine for a one-off whose output is
    # committed. openai/gpt-oss-120b drafted a full set at 54 counted of 197
    # (2026-10-05), paraphrasing spans and asking about paper internals. Both
    # are reasoning models: max_tokens must leave room for thinking or the
    # reply is empty.
    golden_draft_model: str = "stealth/space-bunny-alpha"
    golden_check_model: str = "meta/muse-spark-1.3-contributor"
    golden_api_base_url: str = "https://openrouter.ai/api"
    # Candidates drafted per GoldenType. More are drafted than kept: the checks
    # cull, and the survivors are the set. Seeded, so a redraft samples the
    # same source chunks.
    golden_quota: dict[str, int] = {
        "single_hop": 45,
        "exact_match": 35,
        # Short-query rule (2026-10-04): at 15 each, 4 multi_hop and 1
        # known_hard survived the naturalness check; table-cell and
        # paper-context questions do not read as searches.
        "multi_hop": 35,
        "known_hard": 45,
        "vocabulary_mismatch": 60,
    }
    golden_seed: int = 20260930
    # Source chunks under this many tokens are section stubs with nothing to
    # ask about; the 1,000-token cap (chunk_size_tokens) bounds the top.
    golden_min_chunk_tokens: int = 250
    # A term in at most this many of the ~40k chunks is "rare": a non-
    # exact_match question may not repeat one from its source chunk, or it is
    # a keyword match rather than a test of retrieval. Also the ceiling on an
    # exact_match anchor term, so the anchor is distinctive, not common.
    golden_rare_term_max_df: int = 40
    # A vocabulary_mismatch question may share no word with its chunk that
    # sits in at most this many chunks: everyday field words ("model",
    # "robot", "attack") stay usable, so the question reads like a person's,
    # while every word that would let BM25 single the chunk out is barred.
    golden_mismatch_max_shared_df: int = 500
    # A multi_hop pair shares at least this many rare terms (df at most
    # golden_rare_term_max_df): the same method, model or dataset named in two
    # sections, so one natural query can need both. Random same-paper pairs
    # gave unrelated facts that only a stapled two-part question joins, and
    # the checker culled 16 of 21 as unnatural (2026-10-05).
    golden_multi_hop_min_shared_terms: int = 3
    # A golden question is what a researcher types into a paper search, not a
    # prompt: the first set averaged 35 words of scene-setting no searcher
    # writes (owner directive 2026-10-04). Longer drafts are culled.
    golden_question_max_words: int = 12
    # LLM-judge (#17/#18/answer-eval issue): faithfulness + citation-accuracy
    # scoring on the full agent loop. A different model FAMILY than
    # agent_model (Haiku) by design — judging a model with itself masks the
    # failure modes it's blind to (D14 amendment, "judge hygiene").
    judge_model: str = "claude-opus-4-8"
    # Backend + model are a PAIR: "local" expects a Hugging Face model id,
    # "voyage" expects a Voyage model name (voyage-4-lite is the parked-but-
    # working operating point — DECISIONS.md 2026-07-05, D5 amendment),
    # "openrouter" an OpenRouter model slug (D5 third amendment, 2026-09-18).
    # Flipping the backend alone is not a swap: the model, dims, price and
    # revision below must move with it, or the run fails on the first call
    # with "model does not exist".
    embedding_backend: Literal["local", "voyage", "openrouter"] = "openrouter"
    embedding_model: str = "perplexity/pplx-embed-v1-0.6b"
    embedding_dims: int = 512  # a documented trained MRL point for this model (D5)
    # Local backend only: HF revision pin so a model-card force-push can't
    # silently change our vectors; weights cache under corpus/ (gitignored),
    # never committed.
    embedding_model_revision: str = "e9b6763023c676ca8431644204f50c2b100d9aab"
    embedding_cache_dir: Path = _REPO_ROOT / "corpus" / "models"
    # Asymmetric retrieval prompts — MANDATORY for nomic (model card).
    # Ingest prepends doc_prefix; the query side (#16) MUST prepend
    # query_prefix or recall silently degrades.
    embedding_doc_prefix: str = "search_document: "
    embedding_query_prefix: str = "search_query: "

    # --- API keys (env-only; standard names, no ASKRAG_ prefix) -----------
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY"
    )
    voyage_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="VOYAGE_API_KEY")
    # Cheap-first provider validation seam (#23, owner directive 2026-07-06):
    # empty => the anthropic SDK's real-Anthropic default (prod, D3 intact).
    # Set to OpenRouter's Anthropic-compatible base (no trailing /v1 — the SDK
    # appends /v1/messages itself) to route the loop through `smoke_model`
    # instead, for a cheap live smoke before spending on Haiku. Prod serving
    # never sets this.
    agent_api_base_url: str = ""
    openrouter_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="OPENROUTER_API_KEY"
    )
    # Smoke-only model, routed through OpenRouter when agent_api_base_url is
    # set. Prod agent stays `agent_model` (Haiku, D3) regardless.
    # Version-pinned (not a floating `-latest` alias): a smoke model that
    # silently changes under us turns "the loop still works" into an
    # unrepeatable observation. DeepSeek V4 Flash until the account's
    # guardrail dropped it (2026-10-05).
    smoke_model: str = "xiaomi/mimo-v2.6-flash"

    # --- ingest: extraction (D6) -------------------------------------------
    extract_workers: int = 8  # process pool size; extraction is CPU-bound C
    # 0 = no cap. When a --limit SAMPLE is built, PDFs over this page count
    # are excluded from selection first (owner directive 2026-07-05: one
    # 398-page monograph was 10% of all working-sample chunks, distorting
    # it). Full-corpus runs ignore the cap; excluded papers are not
    # skiplisted — they are valid, just not sample material. Applies at the
    # next sample rebuild; the current working corpus is NOT regenerated.
    sample_max_pages: int = 0

    # --- ingest: the landing page's index frontier (select_frontier.py) ----
    # These two numbers ARE the page's scope. Raising either widens what the
    # page claims and what must therefore be chunked and embedded — the cost
    # is roughly linear: 50 x 8 is ~272 papers and ~11k chunks, and every one
    # of them has to be readable or a link on the page dead-ends.
    frontier_top_cited: int = 50
    frontier_citers_per_work: int = 8
    # Author lists on frontier-model reports run to a thousand names — Llama 3
    # alone is 60 KB of them, and 94% of an untrimmed /api/landing payload was
    # authors the UI never shows. Trimmed SERVER-side so the wire carries what
    # is displayed, not what the catalog happens to hold. Measured 2026-08-28
    # over the real graph: 133,044 -> 10,893 bytes for the top-40 page.
    landing_max_authors: int = 6
    # An id-month joins the stated cohort when it contributed at least this
    # share of the papers we parsed references from (routes_landing.
    # cohort_months). Measured 2026-09-15: 2607 gave 61%, 2608 36%, 2609
    # 1.3%, the next month 0.24% — any value between 0.003 and 0.013 selects
    # the same three months, which is why a threshold is tolerable at all.
    landing_cohort_min_share: float = 0.01
    # A month may be described as arXiv's output only when we hold at least
    # this much of what the catalog lists for it (routes_census). Measured
    # 2026-09-16: July 2026 99.95%, August 99.99%, September 8% — September is
    # not a thin month at arXiv, it is a month the mirror has not published
    # yet (its folder stops at 2609.04203), so a census panel that included it
    # would report a collapse in cs output that did not happen.
    landing_census_min_coverage: float = 0.9
    # Works listed in the uptake panel. A cap for layout, never a claim: the
    # panel states how many works and citations the pair of months holds.
    landing_uptake_limit: int = 8

    # The catalog filter pages over all 65,503 papers, so the page size is a
    # scroll-length decision rather than a cost one: every filter is an index
    # lookup or a 65k-row scan under 150ms.
    catalog_page_size: int = 30

    # --- catalog thumbnails (render_thumbnails) --------------------------
    # Rendered at 320px wide and displayed at up to 160: exactly 2x for a
    # retina screen. Raising it is not a layout tweak — low resolution is what
    # makes the crop fair use for the papers under arXiv's default licence
    # (D19), so this number is a compliance setting.
    thumbnail_width: int = 320
    thumbnail_quality: int = 72
    # How far into a paper to look for a figure. Past the first few pages a
    # picture is a result plot rather than the one that says what the paper
    # is, and every page scanned is a page parsed for every paper.
    thumbnail_scan_pages: int = 8
    # What separates a figure from a logo, measured where the thing is PLACED
    # on the page rather than in its own pixels: a 2000px logo placed at 20pt
    # is a logo. Both floors must hold, plus the share of the page, so a wide
    # flat rule and a small inline glyph each fall out.
    thumbnail_min_figure_width_pt: float = 120.0
    thumbnail_min_figure_height_pt: float = 90.0
    thumbnail_min_figure_page_fraction: float = 0.03
    # And the ceiling, which only the vector path needs: paths that sprawl
    # across most of a page are a table's rules or a boxed author list, not a
    # figure. Measured 2026-09-16 over 120 recent papers — without this,
    # whole pages of dense text were picked as the thumbnail.
    thumbnail_max_figure_page_fraction: float = 0.45
    # How close two vector paths must be to count as one drawing. A figure is
    # hundreds of separate strokes; this is what makes them one object again.
    thumbnail_cluster_gap_pt: float = 12.0
    # Whitespace trimming. The probe is a small greyscale render of the clip,
    # scanned for rows and columns that carry ink: a page is a quarter margin
    # by area, and at thumbnail size those margins are most of the tile.
    thumbnail_trim_probe_px: int = 160
    # 0-255. Anti-aliased text edges land in the 240s, so the threshold sits
    # just under paper white rather than at mid grey.
    thumbnail_trim_ink_level: int = 250
    thumbnail_trim_padding_pt: float = 4.0

    # --- chunking (D7; defaults until evals — revisit trigger in D7) ------
    chunk_size_tokens: int = 1000
    chunk_overlap_ratio: float = 0.15
    # cl100k_base sizes chunks and batches. Voyage bills on its own tokenizer
    # (D5 amendment), so stored n_tokens are estimates there — batch caps and
    # --estimate carry margin for the difference; billing truth is API usage.
    tokenizer_encoding: str = "cl100k_base"
    # 0 = no merge (current strict-D7 behavior). The eval-sweep knob wired in
    # #19: chunk COUNT is eval-gated (D7 revisit + D14), not a target, so
    # tail-merge of sub-threshold chunks stays disabled until evals measure
    # whether the small-chunk tail hurts recall (DECISIONS.md 2026-07-05).
    chunk_min_tokens: int = 0

    # --- ingest: embedding (D5 as amended; DECISIONS.md 2026-07-05) ---------
    # Prices the --estimate for API backends; local runs cost $0 by
    # construction. Perplexity's embed tier on OpenRouter, verified against a
    # billed call 2026-09-18 (11 tokens, $4.4e-08); voyage-4-lite's parked
    # path lists at $0.02.
    embedding_usd_per_mtok: float = 0.004
    # Batch caps size one encode/POST call and one resume shard. Defaults fit
    # the local backend. The parked Voyage path on an unpaid account must
    # retune via env — measured 2026-07-05 (Voyage 429 body): no-payment
    # accounts get 3 RPM / 10K TPM (docs' 2,000 RPM / 16M TPM is Tier 1,
    # payment method added), so use max_tokens≈9000 + pause≈62 there
    # (cl100k ≈ Voyage tokens, measured ratio 1.009).
    # 1,024-chunk shards keep the encode loop hot (an idle process between
    # small shard writes is an eviction target under memory pressure —
    # coordinator diagnosis 2026-07-05); with ~560-token mean chunks the
    # items cap binds first.
    embed_batch_max_items: int = 1024
    embed_batch_max_tokens: int = 1_000_000
    # OpenRouter's embeddings endpoint documents no caps and defers to the
    # provider, so these are MEASURED from Perplexity's own 400s (2026-09-18):
    # "input array exceeds maximum of 512 items" and "Input total size exceeds
    # maximum number of allowed tokens: got 131150, maximum is 120000".
    # The token cap is counted in cl100k (what chunks.jsonl stores) against a
    # limit the provider counts in its own tokenizer, which runs higher: a
    # batch of 119,565 cl100k tokens was 129,339 to Perplexity (+8.2%,
    # 2026-10-02), another +15.8%. 105k keeps most batches under it, and
    # embed_chunks splits the rest on the provider's 400.
    openrouter_embed_batch_max_items: int = 512
    openrouter_embed_batch_max_tokens: int = 105_000
    # Paced in cl100k tokens (what chunks.jsonl stores), which measured ~6%
    # under the provider's own count (20.02M ours vs 21.24M billed over the
    # full corpus), so this targets ~1.9M provider tokens/minute — the rate
    # that embedded 11M tokens without a single 429. The burst matters more
    # than the average, which is why token_bucket.py banks nothing.
    openrouter_embed_tokens_per_min: int = 1_800_000
    # Inner encode() micro-batch for the local backend. Measured 2026-07-05
    # on M-series MPS with ~1k-token chunks: 16 → 0.25s/chunk; the ST default
    # (32) tips unified memory into thrash (~7.5s/chunk, 30x slower).
    embed_encode_batch_size: int = 16
    # Local backend working-set controls (coordinator diagnosis 2026-07-05:
    # an fp32 run at the model-default 8192 seq length swapped out on a
    # loaded box — 9MB worker RSS, chaotic batch times, 28.5 chunks/min).
    # float16 halves model+activation memory (retrieval-quality impact
    # negligible); max_seq caps activation size — measured over all 7,974
    # working-corpus chunks with the nomic tokenizer: p99=1,290 model
    # tokens, only 3 chunks exceed 1,536 (max 3,747; their tails truncate,
    # acceptable for retrieval) vs the 8192 model default.
    # float16 is right on the ingest Mac (MPS runs it natively and it halves
    # the resident set). On a CPU-only box it is a TRAP: torch has no native
    # fp16 kernels there and emulates per-op, measured 2026-08-28 on the ARM
    # VPS at >30x SLOWER than float32 (fp32 0.35 chunks/s vs fp16 ~0.01).
    # Override with ASKRAG_EMBED_LOCAL_DTYPE=float32 wherever embedding runs on
    # CPU — same per-box shape as `embed_device` below.
    embed_local_dtype: Literal["float16", "float32"] = "float16"
    embed_max_seq_tokens: int = 1536
    # "" = library auto-pick (MPS on this Mac); "cpu" is the measured
    # fallback if MPS+swap loses to plain CPU on a loaded box.
    embed_device: str = ""
    embed_batch_pause_seconds: float = 0.0
    embed_retry_max_attempts: int = 6
    embed_retry_base_seconds: float = 2.0
    embed_request_timeout_seconds: float = 120.0

    # --- ingest: index build (D4; issue #14) --------------------------------
    # One Chroma .add() per batch; 1.x rejects batches in the several-
    # thousands, and index build is offline so throughput tuning is moot.
    chroma_add_batch_size: int = 1000

    # --- retrieval (D8; defaults until measured) --------------------------
    rrf_k: int = 60
    # Also the retrieval evals' cutoff (#18): they score the k the agent
    # reads, since recall past it describes passages the agent never sees.
    search_top_k: int = 10
    # The evals' second depth: the candidates a reranker would reorder into
    # the top search_top_k. Recall here is the most any reordering can reach.
    eval_pool_k: int = 50
    rerank_enabled: bool = False  # ships only if evals justify it (D8)
    # The cross-encoder the evals score (D8 amendment 2026-10-05): local,
    # Apache-2.0, 149M parameters, CPU-sized for the build host. Pinned like
    # the embedding model, so a model-card push cannot move the numbers.
    rerank_model: str = "Alibaba-NLP/gte-reranker-modernbert-base"
    rerank_model_revision: str = "f7481e6055501a30fb19d090657df9ec1f79ab2c"
    # Query plus a whole chunk: chunks run to chunk_size_tokens (1,000), and
    # the model reads 8,192, so nothing is cut short.
    rerank_max_tokens: int = 1280
    rerank_batch_size: int = 16

    # --- tools (§5) ----------------------------------------------------------
    # search_corpus clamps a model-supplied k to this ceiling — a pathological
    # tool call can't ask for the whole corpus in one shot.
    search_corpus_max_k: int = 25
    # read_paper's model-facing token budget (§6c row 1: "the model may read
    # full text via read_paper" — a real deep-read, not the ≤50w/≤3-quote
    # display cap, which moved to answer-assembly/#23/#30, DECISIONS.md
    # 2026-07-06). 16,000 ≈ 20% of message_token_budget: generous enough to
    # cover a full short arXiv CS paper's chunks (~1,000 tokens/chunk, D7) or
    # a substantial page range of a longer one, while still leaving room for
    # several more tool calls within one message's budget (max_tool_steps_
    # per_message=8) instead of one read_paper call alone spending it.
    read_paper_max_tokens: int = 16_000

    # --- agent loop (D1/D2) ------------------------------------------------
    max_tool_steps_per_message: int = 8
    # The API's required per-call output cap (a generation ceiling, not a
    # context-window budget — message_token_budget governs that). D3's
    # arithmetic assumes ~2k output tokens per step; this leaves headroom for
    # a longer synthesis turn without being large enough to blow the budget
    # on its own.
    agent_max_output_tokens: int = 4096

    # --- budget caps (D11; every layer server-enforced) --------------------
    # A typical 5-step turn is ~50k in + ~2k out (D3 arithmetic); the
    # per-message budget bounds the pathological turn, not the typical one.
    message_token_budget: int = 80_000
    session_message_cap: int = 15
    ip_daily_spend_cap_usd: float = 0.10
    global_daily_spend_cap_usd: float = 0.50  # trips into replay mode (D11)
    # Salt for the per-IP budget key (D11): raw IPs are NEVER stored — traces.py
    # persists salted SHA-256 only (privacy posture, §6). Set in prod .env so
    # hashes are not reversible via a public rainbow table; the empty default
    # still hashes (dev/tests), it just isn't secret.
    trace_ip_hash_salt: SecretStr = Field(default=SecretStr(""))

    # --- telemetry (D15) ----------------------------------------------------
    telemetry_enabled: bool = True
    # Empty => JSON lines on stdout only (zero network by construction);
    # set => OTLP HTTP export attaches in addition, no code change.
    otlp_endpoint: str = ""
    log_level: str = "INFO"

    # --- query_metadata limits (§5; defaults until measured) ---------------
    # Top-N cap on a count_papers histogram's distinct groups (renamed from
    # the old raw-SQL row cap, DECISIONS.md 2026-07-06 — the enum'd `op`
    # union has no free-form row-returning path left to cap).
    query_metadata_histogram_max_groups: int = 500

    # --- sandbox rlimits (D10) ---------------------------------------------
    # Only the resource numbers are tunable. `--network none`, ro-mounts,
    # non-root, fresh-container-per-call are invariants of runner.py (§6),
    # deliberately not configuration.
    sandbox_cpus: int = 1
    sandbox_memory_mb: int = 512
    sandbox_timeout_seconds: int = 30

    # --- content display caps (§6c; server-enforced, legal posture) --------
    quote_max_words: int = 50
    max_quotes_per_paper: int = 3
    # What counts AS a quote for the ≤3 rule. §6c fixes the 50-word cap and the
    # 3-quote limit but never defines the floor, and the floor decides whether
    # the rule is usable: at 6 words a live Qwen3 answer tripped it 9 times on
    # ordinary technical phrasing ("increasing the proportion of STEM, coding,
    # reasoning"), which is shared terminology, not an excerpt. Row 4's stated
    # target is substantial verbatim quotes and sequential-excerpt section
    # reconstruction; neither is reachable in runs this short. Measured
    # 2026-08-28, DECISIONS.md.
    quote_min_words: int = 15

    # --- chat API (#30; D11/D13) --------------------------------------------
    # Ephemeral, server-side, in-memory session lifetime — a session's LIVE
    # message history is lost after this much inactivity (§6 posture: no
    # durable cross-session state beyond traces.db). One process, so a plain
    # TTL suffices; no Redis (D13 single-VPS, single FastAPI process).
    session_ttl_seconds: int = 3600
    # The frontend dev origin(s) allowed to call the API cross-origin. Empty
    # by default (same-origin prod behind Caddy, D13); #26 sets this via env
    # for local `pnpm dev` against `just serve`.
    cors_allowed_origins: list[str] = Field(default_factory=list)

    # --- derived paths (spec §4c corpus/ tree; one root, one rule) ---------
    @property
    def corpus_db_path(self) -> Path:
        return self.corpus_dir / "corpus.db"

    @property
    def chroma_dir(self) -> Path:
        return self.corpus_dir / "chroma"

    @property
    def extracted_dir(self) -> Path:
        return self.corpus_dir / "extracted"

    @property
    def chunks_jsonl_path(self) -> Path:
        # One chunk record per line (D7 output): streamable into embed_chunks,
        # greppable, rebuilt in full each run so ids stay deterministic.
        return self.corpus_dir / "chunks.jsonl"

    @property
    def embedding_model_slug(self) -> str:
        # Keys every embedding artifact so two models' outputs can never mush
        # together (D5 per-model provenance): short model name + dims.
        name = self.embedding_model.split("/")[-1].lower()
        return f"{name}_{self.embedding_dims}"

    @property
    def embed_batch_limits(self) -> tuple[int, int]:
        """(max_items, max_tokens) for one embed call, for the ACTIVE backend.

        Resolved here rather than at the call site so a backend flip cannot
        leave the caps describing the previous provider — the failure that
        shape produces is a 400 on the first batch of a long run.
        """
        if self.embedding_backend == "openrouter":
            return self.openrouter_embed_batch_max_items, self.openrouter_embed_batch_max_tokens
        return self.embed_batch_max_items, self.embed_batch_max_tokens

    @property
    def embed_tokens_per_minute(self) -> int:
        """Pace for bulk embedding; 0 means unpaced (local, and Voyage, which
        pauses between batches instead — `embed_batch_pause_seconds`)."""
        return self.openrouter_embed_tokens_per_min if self.embedding_backend == "openrouter" else 0

    @property
    def vectors_dir(self) -> Path:
        return self.corpus_dir / "vectors"

    @property
    def vectors_parquet_path(self) -> Path:
        return self.vectors_dir / f"{self.embedding_model_slug}.parquet"

    @property
    def vectors_shards_dir(self) -> Path:
        # One shard per embedded batch; merged into the per-model parquet at
        # the end of a complete run (embed_chunks resume mechanism, D5).
        return self.vectors_dir / f"{self.embedding_model_slug}_shards"

    @property
    def skiplist_path(self) -> Path:
        return self.corpus_dir / "skiplist.json"

    @property
    def arxiv_db_path(self) -> Path:
        # The collector's index — ingest input, never served (spec §4c).
        return self.corpus_dir / "arxiv.db"

    @property
    def pdfs_dir(self) -> Path:
        # The collector's {YYYY}/{MM}/{arxiv_id}.pdf tree — extraction input,
        # local only, never deployed (D9/§4c).
        return self.corpus_dir / "pdfs"

    @property
    def thumbs_dir(self) -> Path:
        # Flat {arxiv_id}.jpg, and the cache rather than an artifact: a file
        # here means that paper's card image has been rendered, and its
        # absence means the next request will render it (D19). Caddy serves
        # it directly and the api writes into it, so unlike every other
        # corpus path this one is deployed and writable.
        return self.corpus_dir / "thumbs"

    @property
    def kaggle_seed_path(self) -> Path:
        # Kaggle arxiv-metadata snapshot zip: the only source that carries
        # per-paper license (§6b metadata duty; build_indexes reads it).
        return self.corpus_dir / "archive.zip"

    @property
    def text_dir(self) -> Path:
        # The collector's {YYMM}/{arxiv_id}.txt plain-text tree. Distinct from
        # extracted_dir, which holds the richer per-paper JSON (markdown,
        # sections, page map) the chunker needs; this tree is flat text and is
        # what the citation graph is read from.
        return self.corpus_dir / "text"

    @property
    def citations_path(self) -> Path:
        # (citing_id, cited_id) edge list — extract_citations' output, an input
        # to resolve_cited_works and build_indexes.
        return self.corpus_dir / "citations.tsv"

    @property
    def frontier_path(self) -> Path:
        # The index manifest: the papers the landing page names, and therefore
        # the papers the agent must be able to read (select_frontier.py).
        return self.corpus_dir / "frontier.json"

    @property
    def cited_works_path(self) -> Path:
        # Catalog metadata for cited works we may never hold text for —
        # resolve_cited_works' output, an input to build_indexes.
        return self.corpus_dir / "cited_works.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
