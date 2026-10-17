"""The per-source eval settings (D21)."""

import pytest
from askrag.config import Settings

from evals import golden_set, rewrite_queries, run_store
from evals.eval_sources import EVAL_SOURCES
from evals.golden_set import GoldenType


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def test_arxiv_keeps_the_committed_paths_and_models():
    ev, s = EVAL_SOURCES["arxiv"], Settings()
    assert ev.golden_path(s) == golden_set.GOLDEN_PATH
    assert ev.runs_dir(s) == run_store.RUNS_DIR
    assert ev.rewrites_path == rewrite_queries.REWRITES_PATH
    assert ev.draft_model(s) == s.golden_draft_model
    assert ev.eval_settings(s) == s


def test_transcripts_keep_their_set_and_runs_under_the_private_dir(tmp_path):
    ev, s = EVAL_SOURCES["claude_transcripts"], Settings(corpus_dir=tmp_path)
    for path in (ev.golden_path(s), ev.drafted_path(s), ev.progress_path(s), ev.runs_dir(s)):
        assert path.is_relative_to(s.transcripts_dir)
    assert ev.rewrites_path is None


def test_transcripts_embed_like_the_corpus_and_rerank_locally(tmp_path):
    s = Settings(corpus_dir=tmp_path)
    run = EVAL_SOURCES["claude_transcripts"].eval_settings(s)
    assert run.embedding_model_slug == s.embedding_model_slug
    assert run.rerank_backend == "local"


def test_transcripts_draft_on_the_anthropic_api_with_two_models(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    ev, s = EVAL_SOURCES["claude_transcripts"], Settings()
    assert ev.draft_model(s) != ev.check_model(s)
    # Anthropic model ids, not OpenRouter's provider/model slugs.
    assert "/" not in ev.draft_model(s) and "/" not in ev.check_model(s)
    assert ev.client(s).client.base_url.host == "api.anthropic.com"


@pytest.mark.parametrize("name", sorted(EVAL_SOURCES))
def test_every_quota_type_has_a_brief(name):
    ev = EVAL_SOURCES[name]
    for type_name, n in ev.quota(Settings()).items():
        if n:
            assert GoldenType(type_name) in ev.prompts.type_briefs
