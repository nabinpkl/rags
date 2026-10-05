"""Query-time embedding for retrieval (D5) — the "query" role of one factory.

The corpus-batch role lives in ingest/embed_chunks.py; both sides construct
their backend through the SAME `make_backend`, differing only in
`input_kind`, so the asymmetric-prefix pairing (search_document: at ingest,
search_query: here — mandatory per the model card, silent recall
degradation if missed) can never drift apart.

One QueryEmbedder instance lives for the process lifetime (the local model
loads once — cold-load cost is real, see #16 measurements); `embed_query`
is the hot path.
"""

import httpx

from askrag import telemetry
from askrag.config import Settings
from askrag.ingest.embed_chunks import EmbeddingError, EmbeddingsBackend, make_backend


class QueryEmbedder:
    """One query string -> one vector, via the process-wide backend."""

    def __init__(self, settings: Settings, backend: EmbeddingsBackend | None = None) -> None:
        # `backend` is the test seam; production always builds the real one
        # in query mode (the contract this module exists to enforce).
        self._backend = (
            backend if backend is not None else make_backend(settings, input_kind="query")
        )
        self._slug = settings.embedding_model_slug

    def embed_query(self, text: str) -> list[float]:
        return self.embed_query_priced(text)[0]

    def embed_query_priced(self, text: str) -> tuple[list[float], float | None]:
        """The vector and the provider's billed dollars (None where the
        backend reports no price); the evals' per-query cost reads this."""
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.embed_query") as span:
            span.set_attribute("askrag.model_slug", self._slug)
            try:
                result = self._backend.embed([text])
                return result.vectors[0], result.usd
            except httpx.TransportError as exc:
                # A genuine transport-level outage (connection refused, DNS,
                # timeout — no HTTP response at all): translate into OUR
                # vocabulary so hybrid_search's fail-soft boundary degrades
                # to BM25-only without knowing httpx exists (PR #59 review
                # finding 2). A non-retryable 4xx (`httpx.HTTPStatusError`,
                # raised unwrapped by `VoyageEmbeddings.embed` for our own
                # bug/bad request) is deliberately NOT caught here — it must
                # propagate and fail loud, never degrade.
                raise EmbeddingError(f"embedding request failed: {exc}") from exc
