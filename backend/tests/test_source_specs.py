"""Tests for askrag.sources.source_specs."""

import re
from pathlib import Path

import pytest

from askrag.config import Settings
from askrag.sources.source_specs import SOURCES


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def test_every_source_names_itself_and_an_index():
    settings = Settings()
    for name, spec in SOURCES.items():
        assert spec.name == name
        assert (
            spec.index(settings).collection == spec.search_settings(settings).embedding_model_slug
        )


def test_the_sources_keep_separate_index_files():
    settings = Settings()
    paths = {spec.index(settings).db_path for spec in SOURCES.values()}
    assert len(paths) == len(SOURCES)


def test_transcripts_never_embed_through_a_hosted_api():
    local = SOURCES["claude_transcripts"].search_settings(Settings(embedding_backend="openrouter"))
    assert local.embedding_backend == "local"
    assert not local.rerank_enabled


def test_no_deploy_mount_reaches_a_private_source():
    """D21: the transcripts index is never served. compose mounts corpus
    paths one by one, so none may name sources/ or the whole corpus dir."""
    compose = Path(__file__).resolve().parents[2] / "deploy" / "compose.yml"
    mounts = re.findall(
        r"^\s*-\s*\$\{ASKRAG_CORPUS_HOST_DIR:-\.\./corpus\}(\S*?):", compose.read_text(), re.M
    )
    assert mounts, "no corpus mounts found: the pattern drifted from compose.yml"
    assert all(m.startswith("/") and m != "/" for m in mounts)
    assert not [m for m in mounts if m.startswith("/sources")]
