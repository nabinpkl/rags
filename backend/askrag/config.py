"""Every tunable and all environment access in ONE pydantic-settings class.

House rule (spec §4c/§4d, issue #10 acceptance): this is the only module that
reads the environment — `os.environ` / `os.getenv` must appear nowhere else in
askrag. Enforced by tests/test_config.py, which scans the source tree.
"""

from functools import lru_cache
from pathlib import Path

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
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 512  # Matryoshka truncation (D5)

    # --- API keys (env-only; standard names, no ASKRAG_ prefix) -----------
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY"
    )
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")

    # --- ingest: extraction (D6) -------------------------------------------
    extract_workers: int = 8  # process pool size; extraction is CPU-bound C

    # --- chunking (D7; defaults until evals — revisit trigger in D7) ------
    chunk_size_tokens: int = 1000
    chunk_overlap_ratio: float = 0.15
    # cl100k_base matches text-embedding-3-small (D5); chunk token counts must
    # be measured with the same encoding the embedder bills on.
    tokenizer_encoding: str = "cl100k_base"
    # 0 = no merge (current strict-D7 behavior). The eval-sweep knob wired in
    # #19: chunk COUNT is eval-gated (D7 revisit + D14), not a target, so
    # tail-merge of sub-threshold chunks stays disabled until evals measure
    # whether the small-chunk tail hurts recall (decisions.md 2026-07-05).
    chunk_min_tokens: int = 0

    # --- retrieval (D8; defaults until measured) --------------------------
    rrf_k: int = 60
    search_top_k: int = 10
    rerank_enabled: bool = False  # ships only if evals justify it (D8)

    # --- agent loop (D1/D2) ------------------------------------------------
    max_tool_steps_per_message: int = 8

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
    query_metadata_max_rows: int = 500
    query_metadata_timeout_seconds: float = 2.0

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
    def vectors_parquet_path(self) -> Path:
        return self.corpus_dir / "vectors.parquet"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
