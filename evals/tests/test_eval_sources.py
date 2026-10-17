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


def test_transcripts_keep_everything_private_and_local(tmp_path):
    ev, s = EVAL_SOURCES["claude_transcripts"], Settings(corpus_dir=tmp_path)
    for path in (ev.golden_path(s), ev.drafted_path(s), ev.progress_path(s), ev.runs_dir(s)):
        assert path.is_relative_to(s.transcripts_dir)
    assert ev.rewrites_path is None
    local = ev.eval_settings(s)
    assert (local.embedding_backend, local.rerank_backend) == ("local", "local")
    assert ev.draft_model(s) != ev.check_model(s)


@pytest.mark.parametrize("name", sorted(EVAL_SOURCES))
def test_every_quota_type_has_a_brief(name):
    ev = EVAL_SOURCES[name]
    for type_name, n in ev.quota(Settings()).items():
        if n:
            assert GoldenType(type_name) in ev.prompts.type_briefs
