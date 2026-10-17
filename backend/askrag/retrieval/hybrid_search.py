"""Hybrid retrieval (D8) over any source's index (D21): vector + BM25 legs,
RRF fusion, filters pushed down, then a reranker reorders the fused pool into
the top k.

`search()` is the interface tools, evals and the `just ask` CLI consume; it
returns ScoredChunk with full provenance (section + position anchors are what
make citations verifiable, D7/D9). Fusion is reciprocal rank fusion —
1/(rrf_k + rank), summed across legs — so no leg weights to tune (D8). The
index is whatever `IndexLocation` the caller hands in; this module reads only
the index contract (index_schema.py) and never names a source.

Degradation contract (D8, deliberate): the VECTOR leg failing (model gone,
API outage on the parked path) degrades to BM25-only results with a warning
— the site limps, it does not die. Only the operational error set
(`_VECTOR_LEG_OPERATIONAL_ERRORS`) triggers this, expressed ENTIRELY in this
codebase's own exception vocabulary (`VectorStoreError`, `EmbeddingError`,
raw `OSError`) — this module never names an httpx or chromadb type itself;
`vector_store.py` and `embeddings.py` translate their own library's
operational errors into that vocabulary at their own boundary (a code bug
there stays raw and propagates, PR #59 review findings 2/3). A code bug in
the embed/query path fails loud instead of degrading (2026-07-06 checkpoint
finding 3). The index db failing is fatal by design: without it there is no
text to return at all.

Rerank (config.rerank_enabled, D8 amendment 2026-10-14): both legs retrieve
`rerank_pool_k` deep, fusion keeps that many, and the hosted reranker picks
the top k. A reranker outage (`RerankUnavailable`) keeps the fused order with
a warning, the same limp-not-die contract as the vector leg; any other rerank
failure is a bug and propagates. `search_priced` also returns what the search
billed (query embedding plus rerank) so the agent's turn can count it (D11).
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from askrag import db, telemetry
from askrag.config import Settings
from askrag.retrieval import fts
from askrag.retrieval.embed_chunks import EmbeddingError
from askrag.retrieval.embeddings import QueryEmbedder
from askrag.retrieval.filters import Filters
from askrag.retrieval.index_location import IndexLocation
from askrag.retrieval.index_schema import CHUNKS, DOCUMENTS
from askrag.retrieval.rerank import Reranked, RerankUnavailable, live_reranker
from askrag.retrieval.vector_store import VectorStore, VectorStoreError

# The vector leg's fail-soft set (D8): store/collection unusable, the
# embedding API/model unreachable, or a raw local IO failure — all genuine
# OUTAGES, named ONLY in this codebase's own vocabulary (never an httpx or
# chromadb type — that leaks a library taxonomy up past the
# VectorStoreLike/pgvector seam, D4; PR #59 review findings 2/3). Anything
# else (KeyError, AttributeError, a dimension mismatch, a non-retryable 4xx)
# is a CODE BUG, not an outage, and must fail loud instead of masquerading as
# a silent BM25-only degrade (2026-07-06 checkpoint finding 3).
_VECTOR_LEG_OPERATIONAL_ERRORS = (VectorStoreError, EmbeddingError, OSError)

_log = logging.getLogger("askrag.retrieval.hybrid_search")


@dataclass(frozen=True)
class ScoredChunk:
    """The retrieval product (issue #16 interface): provenance + fused score.

    `pos_start`/`pos_end` are the source's positions (PDF pages for arXiv).
    `leg` records which side(s) surfaced the chunk: "vector", "bm25", "both".
    """

    chunk_id: str
    doc_id: str
    section: str
    pos_start: int
    pos_end: int
    text: str
    # The RRF fusion score. With reranking on, list order is the ranking and
    # this score no longer sorts it.
    score: float
    leg: str
    version: str | None  # the document's revision (arXiv: the D9 pinned-PDF anchor)


def rrf_fuse(legs: dict[str, list[str]], rrf_k: int) -> dict[str, tuple[float, str]]:
    """Reciprocal rank fusion: chunk_id -> (score, leg-provenance).

    score = Σ over legs of 1/(rrf_k + rank), rank 1-based (D8). Pure so the
    RRF math is testable by hand.
    """
    fused: dict[str, tuple[float, str]] = {}
    for leg_name, chunk_ids in legs.items():
        for rank, chunk_id in enumerate(chunk_ids, start=1):
            score, seen = fused.get(chunk_id, (0.0, ""))
            fused[chunk_id] = (
                score + 1.0 / (rrf_k + rank),
                "both" if seen and seen != leg_name else leg_name,
            )
    return fused


@dataclass(frozen=True)
class SearchOutcome:
    """The ranked chunks and the dollars the providers billed for them."""

    chunks: list[ScoredChunk] = field(default_factory=list)
    usd: float = 0.0


class QueryEmbedderLike(Protocol):
    """The embedder seam HybridSearch depends on (tests inject fakes)."""

    def embed_query_priced(self, text: str) -> tuple[list[float], float | None]: ...


class RerankerLike(Protocol):
    """The rerank seam: (query, [(chunk_id, text)], k) -> top k ids and cost."""

    def rerank(self, query: str, candidates: list[tuple[str, str]], k: int) -> Reranked: ...


class VectorStoreLike(Protocol):
    """The store seam — also what a pgvector implementation must satisfy (D4)."""

    def query(self, embedding: list[float], k: int, *, filters: Filters) -> list[str]: ...


class HybridSearch:
    """Both legs + fusion + hydration over one index, holding its resources."""

    def __init__(
        self,
        settings: Settings,
        index: IndexLocation,
        *,
        embedder: QueryEmbedderLike | None = None,
        vector_store: VectorStoreLike | None = None,
        reranker: RerankerLike | None = None,
    ) -> None:
        # Injectable seams for tests; production loads the real model here —
        # the one-time cold cost the FastAPI lifespan will pay once (#30).
        self._settings = settings
        self._index = index
        self._embedder = embedder if embedder is not None else QueryEmbedder(settings)
        self._store = vector_store if vector_store is not None else VectorStore(index)
        if reranker is not None:
            self._reranker: RerankerLike | None = reranker
        elif settings.rerank_enabled:
            self._reranker = live_reranker(settings)
        else:
            self._reranker = None

    def search(
        self, query: str, filters: Filters | None = None, k: int | None = None
    ) -> list[ScoredChunk]:
        return self.search_priced(query, filters, k).chunks

    def search_priced(
        self, query: str, filters: Filters | None = None, k: int | None = None
    ) -> SearchOutcome:
        settings = self._settings
        filters = filters if filters is not None else Filters()
        top_k = k if k is not None else settings.search_top_k
        if not query.strip():
            # A blank query must return nothing, not garbage: the vector leg
            # would otherwise embed the bare task prefix and return whatever
            # sits near it (observed live before this guard existed).
            return SearchOutcome()
        # The reranker reorders a deeper pool than it returns; without one the
        # legs retrieve exactly what the caller reads.
        depth = max(settings.rerank_pool_k, top_k) if self._reranker is not None else top_k
        usd = 0.0
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.search") as span:
            span.set_attribute("askrag.model_slug", settings.embedding_model_slug)
            span.set_attribute("askrag.k", top_k)

            legs: dict[str, list[str]] = {}
            try:
                embedding, embed_usd = self._embedder.embed_query_priced(query)
                # A backend that reports no price runs locally and bills nothing.
                usd += embed_usd or 0.0
                legs["vector"] = self._store.query(embedding, depth, filters=filters)
            except _VECTOR_LEG_OPERATIONAL_ERRORS:
                # Fail-soft BY DESIGN (D8): a dead vector leg degrades to
                # BM25-only, never a dead site. Index db errors below stay
                # fatal — without it there is nothing to return. Narrowed to
                # the operational error set (finding 3): a code bug now
                # propagates instead of silently degrading.
                _log.warning("vector leg failed; degrading to BM25-only (D8)", exc_info=True)
                span.set_attribute("askrag.degraded", True)

            conn = db.connect_corpus(self._index.db_path)
            try:
                with tracer.start_as_current_span("askrag.retrieval.bm25"):
                    legs["bm25"] = fts.search_bm25(conn, query, depth, filters)
                fused = rrf_fuse(legs, settings.rrf_k)
                ranked = sorted(fused.items(), key=lambda kv: kv[1][0], reverse=True)[:depth]
                pool = hydrate(conn, ranked)
            finally:
                conn.close()

            results = pool[:top_k]
            if self._reranker is not None and pool:
                with tracer.start_as_current_span("askrag.retrieval.rerank") as rerank_span:
                    rerank_span.set_attribute("askrag.pool", len(pool))
                    try:
                        reranked = self._reranker.rerank(
                            query, [(c.chunk_id, c.text) for c in pool], top_k
                        )
                    except RerankUnavailable:
                        # Fail-soft like the vector leg (D8): the fused order
                        # stands, and the reader still gets an answer.
                        _log.warning("reranker unavailable; keeping fused order", exc_info=True)
                        span.set_attribute("askrag.rerank_degraded", True)
                    else:
                        usd += reranked.usd
                        by_id = {c.chunk_id: c for c in pool}
                        results = [by_id[chunk_id] for chunk_id in reranked.chunk_ids]

            span.set_attribute("askrag.results", len(results))
            for leg_name, ids in legs.items():
                span.set_attribute(f"askrag.leg.{leg_name}", len(ids))
            span.set_attribute("askrag.usd", usd)
        return SearchOutcome(results, usd)


def hydrate(
    conn: sqlite3.Connection,
    ranked: list[tuple[str, tuple[float, str]]],
) -> list[ScoredChunk]:
    """Fused ids -> full provenance rows, one query, input order kept."""
    if not ranked:
        return []
    ids = [chunk_id for chunk_id, _ in ranked]
    placeholders = ",".join("?" * len(ids))
    rows = {
        row["chunk_id"]: row
        for row in conn.execute(
            f"SELECT c.chunk_id, c.doc_id, c.section, c.pos_start, c.pos_end,"
            f"       c.text, d.version FROM {CHUNKS} c"
            f" JOIN {DOCUMENTS} d ON d.doc_id = c.doc_id"
            f" WHERE c.chunk_id IN ({placeholders})",
            ids,
        ).fetchall()
    }
    return [
        ScoredChunk(
            chunk_id=chunk_id,
            doc_id=rows[chunk_id]["doc_id"],
            section=rows[chunk_id]["section"],
            pos_start=rows[chunk_id]["pos_start"],
            pos_end=rows[chunk_id]["pos_end"],
            text=rows[chunk_id]["text"],
            score=score,
            leg=leg,
            version=rows[chunk_id]["version"],
        )
        for chunk_id, (score, leg) in ranked
    ]
