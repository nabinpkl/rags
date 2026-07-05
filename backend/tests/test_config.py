"""Tests for askrag.config — including the single-env-reader house rule."""

import re
from pathlib import Path
from typing import Any

import pytest

from askrag.config import Settings, get_settings

ASKRAG_SRC = Path(__file__).resolve().parent.parent / "askrag"


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    # Settings resolves env_file=".env" relative to cwd; running from a bare
    # tmp dir keeps a developer's local .env from changing test outcomes.
    monkeypatch.chdir(tmp_path)


def make_settings(**overrides: Any) -> Settings:
    return Settings(**overrides)


def test_spec_constants_load_without_env(monkeypatch):
    import os

    for var in [name for name in os.environ if name.startswith("ASKRAG_")]:
        monkeypatch.delenv(var)
    settings = make_settings()
    assert settings.agent_model == "claude-haiku-4-5-20251001"  # D3
    assert settings.embedding_model == "voyage-4-lite"  # D5 (amended 2026-07-05)
    assert settings.embedding_dims == 512  # D5
    assert settings.chunk_size_tokens == 1000  # D7
    assert settings.chunk_overlap_ratio == 0.15  # D7
    assert settings.max_tool_steps_per_message == 8  # D1
    assert settings.session_message_cap == 15  # D11
    assert settings.global_daily_spend_cap_usd == 0.50  # D11
    assert settings.sandbox_cpus == 1  # D10
    assert settings.sandbox_memory_mb == 512  # D10
    assert settings.sandbox_timeout_seconds == 30  # D10
    assert settings.quote_max_words == 50  # §6c
    assert settings.max_quotes_per_paper == 3  # §6c


def test_env_overrides_with_prefix(monkeypatch):
    monkeypatch.setenv("ASKRAG_CHUNK_SIZE_TOKENS", "512")
    monkeypatch.setenv("ASKRAG_GLOBAL_DAILY_SPEND_CAP_USD", "1.25")
    settings = make_settings()
    assert settings.chunk_size_tokens == 512
    assert settings.global_daily_spend_cap_usd == 1.25


def test_api_keys_use_standard_env_names(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-voy-test")
    settings = make_settings()
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert settings.voyage_api_key.get_secret_value() == "pa-voy-test"
    # SecretStr keeps keys out of reprs/logs.
    assert "sk-ant-test" not in repr(settings)


def test_derived_paths_follow_corpus_dir(tmp_path):
    settings = make_settings(corpus_dir=tmp_path / "corpus")
    assert settings.corpus_db_path == tmp_path / "corpus" / "corpus.db"
    assert settings.chroma_dir == tmp_path / "corpus" / "chroma"
    assert settings.extracted_dir == tmp_path / "corpus" / "extracted"
    assert settings.vectors_parquet_path == tmp_path / "corpus" / "vectors.parquet"
    assert settings.skiplist_path == tmp_path / "corpus" / "skiplist.json"
    assert settings.arxiv_db_path == tmp_path / "corpus" / "arxiv.db"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_config_is_the_only_env_reader():
    # Issue #10 acceptance, grep-verifiable: os.environ / os.getenv appear
    # nowhere in askrag outside config.py (and pydantic-settings does the
    # reading even there).
    env_access = re.compile(r"os\.environ|os\.getenv|getenv\(")
    offenders = [
        str(path)
        for path in ASKRAG_SRC.rglob("*.py")
        if path.name != "config.py" and env_access.search(path.read_text())
    ]
    assert offenders == []
