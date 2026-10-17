"""The retrieval evals' per-source settings (D21): where each source's golden
set and runs live, how it is drafted, and what its searches run under.

arXiv's entries are the paths and models the committed set and runs always
used. The transcripts' entries keep everything under corpus/ (the set quotes
private sessions, so it is never committed), draft with Anthropic models on
the Anthropic API, embed with the corpus embedder and rerank locally, and have
no rewrite row (that row is the agent model's rewrite, and this source has no
agent).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from askrag.config import Settings
from askrag.sources.source_specs import SOURCES, SourceSpec

from evals import draft_progress, golden_set, rewrite_queries, run_store
from evals.draft_prompts import ARXIV, CLAUDE_TRANSCRIPTS, DraftPrompts
from evals.model_client import MessagesClient


@dataclass(frozen=True)
class EvalSource:
    spec: SourceSpec
    prompts: DraftPrompts
    # The set the eval scores (no passages) and the drafted copy (passages).
    golden_path: Callable[[Settings], Path]
    drafted_path: Callable[[Settings], Path]
    progress_path: Callable[[Settings], Path]
    runs_dir: Callable[[Settings], Path]
    rewrites_path: Path | None
    # Where the drafting and checking models are called.
    client: Callable[[Settings], MessagesClient]
    draft_model: Callable[[Settings], str]
    check_model: Callable[[Settings], str]
    quota: Callable[[Settings], dict[str, int]]
    # How many sources one document may give per type.
    per_doc: Callable[[Settings], int]
    # The settings every leg and the rerank row run under.
    eval_settings: Callable[[Settings], Settings]
    # Words for the report: what a document is, and how the vector leg embeds.
    doc_noun: str
    embed_note: str
    cost_note: str


def _transcript_evals(settings: Settings) -> Path:
    return settings.transcripts_dir / "evals"


def _transcript_eval_settings(settings: Settings) -> Settings:
    local = SOURCES["claude_transcripts"].search_settings(settings)
    return local.model_copy(update={"rerank_backend": "local"})


EVAL_SOURCES: dict[str, EvalSource] = {
    "arxiv": EvalSource(
        spec=SOURCES["arxiv"],
        prompts=ARXIV,
        golden_path=lambda s: golden_set.GOLDEN_PATH,
        drafted_path=golden_set.drafted_path,
        progress_path=lambda s: draft_progress.PROGRESS_PATH,
        runs_dir=lambda s: run_store.RUNS_DIR,
        rewrites_path=rewrite_queries.REWRITES_PATH,
        client=MessagesClient.openrouter,
        draft_model=lambda s: s.golden_draft_model,
        check_model=lambda s: s.golden_check_model,
        quota=lambda s: s.golden_quota,
        per_doc=lambda s: 1,
        eval_settings=SOURCES["arxiv"].search_settings,
        doc_noun="paper",
        embed_note="the embedding API call",
        cost_note=(
            "Cost is the mean per question that the providers billed: the embedding,"
            " the rerank and the rewrite call."
        ),
    ),
    "claude_transcripts": EvalSource(
        spec=SOURCES["claude_transcripts"],
        prompts=CLAUDE_TRANSCRIPTS,
        golden_path=lambda s: _transcript_evals(s) / "golden.jsonl",
        drafted_path=lambda s: _transcript_evals(s) / "golden.drafted.jsonl",
        progress_path=lambda s: _transcript_evals(s) / "golden.progress.jsonl",
        runs_dir=lambda s: _transcript_evals(s) / "runs",
        rewrites_path=None,
        client=MessagesClient.anthropic,
        draft_model=lambda s: s.transcripts_golden_draft_model,
        check_model=lambda s: s.transcripts_golden_check_model,
        quota=lambda s: s.transcripts_golden_quota,
        per_doc=lambda s: s.transcripts_golden_per_doc,
        eval_settings=_transcript_eval_settings,
        doc_noun="session",
        embed_note="the embedding API call",
        cost_note="Cost is the mean per question that the providers billed: the embedding.",
    ),
}
