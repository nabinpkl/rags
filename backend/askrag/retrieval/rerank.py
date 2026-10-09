"""Reranking (D8): reorder retrieved chunks by a model that reads the query
and each chunk together.

Two scorers behind one interface: a hosted reranker through OpenRouter's
/rerank (what a live path could afford) and a local cross-encoder (the
comparison point, far too slow on the build host to serve). Eval-only for
now: `rerank_enabled` stays False until the evals justify it (D8), so
nothing on the request path constructs this. Chunk text is only scored,
never returned, so the §6 fencing rules are unaffected; the hosted scorer
sends it to the provider exactly as the agent's model calls do.
"""

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from askrag.config import Settings

_OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"


class RerankError(RuntimeError):
    """The reranker failed or answered out of contract."""


class Scorer(Protocol):
    def score(self, query: str, texts: list[str]) -> tuple[list[float], float]:
        """One relevance score per text, in input order, and the dollars billed."""
        ...


@dataclass(frozen=True)
class Reranked:
    chunk_ids: list[str]  # best first, at most k
    usd: float  # billed by the provider; 0 for the local scorer


class Reranker:
    """(query, [(chunk_id, text)]) -> the top k chunk ids and what it cost."""

    def __init__(self, settings: Settings, scorer: Scorer | None = None) -> None:
        # `scorer` is the test seam; production builds the configured one.
        self._scorer = scorer if scorer is not None else make_scorer(settings)

    def rerank(self, query: str, candidates: Sequence[tuple[str, str]], k: int) -> Reranked:
        if not candidates:
            return Reranked([], 0.0)
        scores, usd = self._scorer.score(query, [text for _, text in candidates])
        if len(scores) != len(candidates):
            raise RerankError(f"reranker scored {len(scores)} of {len(candidates)} candidates")
        # Stable on ties: the retriever's order breaks them.
        order = sorted(range(len(candidates)), key=lambda i: -scores[i])
        return Reranked([candidates[i][0] for i in order[:k]], usd)


def make_scorer(settings: Settings) -> Scorer:
    if settings.rerank_backend == "openrouter":
        return OpenRouterScorer(settings)
    return LocalScorer(settings)


class OpenRouterScorer:
    """OpenRouter's /rerank. Its reply orders results by score and names each
    by input index; the billed cost comes back in `usage.cost`, which is the
    only price used, so a repriced model cannot drift from a rate table."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = settings.openrouter_api_key.get_secret_value()
        if not key:
            raise RerankError("OPENROUTER_API_KEY is not set")
        self._model = settings.rerank_openrouter_model
        self._attempts = settings.rerank_max_attempts
        self._backoff = settings.rerank_backoff_base_seconds
        self._sleep = sleep  # test seam
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {key}"},
            timeout=settings.rerank_request_timeout_seconds,
            transport=transport,
        )

    def score(self, query: str, texts: list[str]) -> tuple[list[float], float]:
        for attempt in range(self._attempts):
            response = self._client.post(
                _OPENROUTER_RERANK_URL,
                json={"model": self._model, "query": query, "documents": texts},
            )
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == self._attempts - 1:
                break
            self._sleep(self._backoff * 2**attempt)
        if response.status_code != 200:
            raise RerankError(f"HTTP {response.status_code} from rerank: {response.text[:200]}")
        payload = response.json()
        scores = [math.nan] * len(texts)
        for result in payload["results"]:
            scores[result["index"]] = float(result["relevance_score"])
        if any(math.isnan(s) for s in scores):
            raise RerankError("rerank reply left some documents unscored")
        cost = payload.get("usage", {}).get("cost")
        if not isinstance(cost, int | float) or isinstance(cost, bool) or cost < 0:
            raise RerankError(f"rerank reply carried no usable cost: {cost!r}")
        return scores, float(cost)


class LocalScorer:
    """The pinned cross-encoder, in process. Bills nothing."""

    def __init__(self, settings: Settings) -> None:
        if not settings.rerank_model_revision:
            raise RerankError("rerank_model_revision must pin a HF commit hash")
        # Deferred: torch's import cost stays off every path that never reranks.
        from sentence_transformers import CrossEncoder

        self._batch_size = settings.rerank_batch_size
        self._model = CrossEncoder(
            settings.rerank_model,
            revision=settings.rerank_model_revision,
            cache_folder=str(settings.embedding_cache_dir),
            max_length=settings.rerank_max_tokens,
        )

    def score(self, query: str, texts: list[str]) -> tuple[list[float], float]:
        scores = self._model.predict([(query, t) for t in texts], batch_size=self._batch_size)
        return [float(s) for s in scores], 0.0
