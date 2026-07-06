"""Chroma wrapper — THE pgvector seam (D4).

Everything Chroma stays behind this module: callers pass primitives and get
chunk_ids back. When D4's revisit trigger fires (>~50k papers / ~1M chunks /
p95 >300ms), pgvector replaces the internals of this file and nothing else.

The collection is looked up BY MODEL SLUG (per-model keying, #13/#14): a
process configured for one embedding model can only ever query that model's
vectors.
"""

from pathlib import Path

import chromadb
import chromadb.config
import chromadb.errors

from askrag import telemetry
from askrag.config import Settings


class VectorStoreError(Exception):
    """The store or the per-model collection is missing/unusable."""


# ChromaError subclasses that mean OUR code passed a bad call (wrong
# embedding dimension, a malformed argument) — code bugs, not outages; these
# must stay loud, never translated to the operational VectorStoreError below
# (PR #59 review finding 3). Every OTHER ChromaError (InternalError,
# RateLimitError, an auth/quota/version failure, ...) is a genuine store-side
# operational failure and gets wrapped.
_CHROMA_CODE_BUG_ERRORS = (
    chromadb.errors.InvalidDimensionException,
    chromadb.errors.InvalidArgumentError,
)


class VectorStore:
    """query(embedding, k, filters) -> rank-ordered chunk_ids."""

    def __init__(self, settings: Settings, chroma_dir: Path | None = None) -> None:
        path = chroma_dir if chroma_dir is not None else settings.chroma_dir
        client = chromadb.PersistentClient(
            path=str(path),
            # Deliberate no-egress (see build_indexes; review #55).
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        self._slug = settings.embedding_model_slug
        try:
            self._collection = client.get_collection(self._slug)
        except chromadb.errors.NotFoundError as exc:
            raise VectorStoreError(
                f"chroma collection '{self._slug}' not found under {path} — "
                "run build_indexes (#14) for this model first"
            ) from exc

    def query(
        self,
        embedding: list[float],
        k: int,
        *,
        category: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
    ) -> list[str]:
        """Nearest chunk_ids; filters push into Chroma's where clause (D8)."""
        clauses: list[dict] = []
        if category is not None:
            clauses.append({"category": category})
        if year_min is not None:
            clauses.append({"year": {"$gte": year_min}})
        if year_max is not None:
            clauses.append({"year": {"$lte": year_max}})
        where = clauses[0] if len(clauses) == 1 else {"$and": clauses} if clauses else None
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.vector") as span:
            span.set_attribute("askrag.model_slug", self._slug)
            span.set_attribute("askrag.k", k)
            try:
                result = self._collection.query(
                    query_embeddings=[embedding], n_results=k, where=where, include=[]
                )
            except _CHROMA_CODE_BUG_ERRORS:
                raise
            except chromadb.errors.ChromaError as exc:
                raise VectorStoreError(f"chroma query failed: {exc}") from exc
        return result["ids"][0]
