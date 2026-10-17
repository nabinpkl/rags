"""Chroma wrapper: THE pgvector seam (D4), for any source's index (D21).

Everything Chroma stays behind this module: callers pass primitives and get
chunk_ids back. When D4's revisit trigger fires (>~50k papers / ~1M chunks /
p95 >300ms), pgvector replaces the internals of this file and nothing else.

The collection is looked up BY MODEL SLUG (per-model keying, #13/#14): a
process configured for one embedding model can only ever query that model's
vectors. Each vector carries the metadata `vector_metadata` builds (doc_id,
day, facet_<key>), which is what `query` filters on.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import chromadb
import chromadb.config
import chromadb.errors

from askrag import telemetry
from askrag.retrieval.filters import Filters
from askrag.retrieval.index_location import IndexLocation


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

_FACET_PREFIX = "facet_"


def _client(chroma_dir: Path) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=str(chroma_dir),
        # No-egress must be deliberate, not an accident of the pin (review #55).
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )


def vector_metadata(
    doc_id: str, day: int, facets: Sequence[tuple[str, str]]
) -> dict[str, str | int]:
    """The metadata one vector carries: one value per facet key."""
    meta: dict[str, str | int] = {"doc_id": doc_id, "day": day}
    for key, value in facets:
        if f"{_FACET_PREFIX}{key}" in meta:
            raise ValueError(f"{doc_id} has two values for facet {key!r}")
        meta[f"{_FACET_PREFIX}{key}"] = value
    return meta


def load_collection(
    chroma_dir: Path,
    collection_name: str,
    ids: list[str],
    vectors: list[list[float]],
    metadatas: Sequence[Mapping[str, str | int]],
    add_batch_size: int,
) -> int:
    """Drop and recreate the per-model collection; returns its count."""
    client = _client(chroma_dir)
    try:
        client.delete_collection(collection_name)
    except chromadb.errors.NotFoundError:  # first build: nothing to drop
        pass
    # Cosine over unit-normalized vectors (embed_chunks normalizes every backend).
    collection = client.create_collection(
        collection_name, configuration={"hnsw": {"space": "cosine"}}
    )
    for start in range(0, len(ids), add_batch_size):
        end = start + add_batch_size
        collection.add(
            ids=ids[start:end],
            # cast only widens list[list[float]] to what chroma declares;
            # list invariance blocks the direct assignment.
            embeddings=cast("list[Sequence[float]]", vectors[start:end]),
            metadatas=[dict(m) for m in metadatas[start:end]],
        )
    return collection.count()


def where_clause(filters: Filters) -> dict | None:
    """Filters -> Chroma's `where`; None when nothing filters."""
    clauses: list[dict] = [{f"{_FACET_PREFIX}{key}": value} for key, value in filters.facets]
    if filters.day_min is not None:
        clauses.append({"day": {"$gte": filters.day_min}})
    if filters.day_max is not None:
        clauses.append({"day": {"$lte": filters.day_max}})
    if filters.doc_ids:
        clauses.append({"doc_id": {"$in": list(filters.doc_ids)}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class VectorStore:
    """query(embedding, k, filters) -> rank-ordered chunk_ids."""

    def __init__(self, index: IndexLocation) -> None:
        self._slug = index.collection
        try:
            self._collection = _client(index.chroma_dir).get_collection(self._slug)
        except chromadb.errors.NotFoundError as exc:
            raise VectorStoreError(
                f"chroma collection '{self._slug}' not found under {index.chroma_dir}: "
                "build this source's index for this model first"
            ) from exc

    def query(self, embedding: list[float], k: int, *, filters: Filters) -> list[str]:
        """Nearest chunk_ids; filters push into Chroma's where clause (D8)."""
        if filters.empty_scope:
            # Empty scope = nothing in scope (see fts.search_bm25). Chroma
            # would reject an empty $in, and returning unscoped results here
            # would silently widen a scope the caller deliberately narrowed.
            return []
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.vector") as span:
            span.set_attribute("askrag.model_slug", self._slug)
            span.set_attribute("askrag.k", k)
            try:
                result = self._collection.query(
                    query_embeddings=[embedding],
                    n_results=k,
                    where=where_clause(filters),
                    include=[],
                )
            except _CHROMA_CODE_BUG_ERRORS:
                raise
            except chromadb.errors.ChromaError as exc:
                raise VectorStoreError(f"chroma query failed: {exc}") from exc
        return result["ids"][0]
