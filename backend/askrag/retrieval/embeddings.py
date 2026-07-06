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

from askrag import telemetry
from askrag.config import Settings
from askrag.ingest.embed_chunks import EmbeddingsBackend, make_backend


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
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.embed_query") as span:
            span.set_attribute("askrag.model_slug", self._slug)
            return self._backend.embed([text]).vectors[0]
