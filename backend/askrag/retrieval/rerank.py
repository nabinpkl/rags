"""Cross-encoder reranking (D8): reorder retrieved chunks by a model that
reads the query and each chunk together.

Eval-only for now: `rerank_enabled` stays False until the evals justify it
(D8), so nothing on the request path constructs this. Chunk text is only
scored, never returned, so the §6 fencing rules are unaffected.
"""

from collections.abc import Sequence
from typing import Protocol

from askrag.config import Settings


class PairScorer(Protocol):
    def predict(self, sentences: list[tuple[str, str]], batch_size: int) -> Sequence[float]: ...


class Reranker:
    """(query, [(chunk_id, text)]) -> chunk ids, best first, top k."""

    def __init__(self, settings: Settings, model: PairScorer | None = None) -> None:
        if not settings.rerank_model_revision:
            raise ValueError("rerank_model_revision must pin a HF commit hash")
        self._batch_size = settings.rerank_batch_size
        # `model` is the test seam; the real one loads once per process.
        self._model = model if model is not None else _load(settings)

    def rerank(self, query: str, candidates: Sequence[tuple[str, str]], k: int) -> list[str]:
        if not candidates:
            return []
        scores = self._model.predict(
            [(query, text) for _, text in candidates], batch_size=self._batch_size
        )
        if len(scores) != len(candidates):
            raise ValueError(f"reranker scored {len(scores)} of {len(candidates)} candidates")
        # Stable on ties: the retriever's order breaks them.
        order = sorted(range(len(candidates)), key=lambda i: -float(scores[i]))
        return [candidates[i][0] for i in order[:k]]


def _load(settings: Settings) -> PairScorer:
    # Deferred: torch's import cost stays off every path that never reranks.
    from sentence_transformers import CrossEncoder

    return CrossEncoder(
        settings.rerank_model,
        revision=settings.rerank_model_revision,
        cache_folder=str(settings.embedding_cache_dir),
        max_length=settings.rerank_max_tokens,
    )
