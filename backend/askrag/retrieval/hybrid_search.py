"""Hybrid retrieval (D8): vector + BM25 legs, RRF fusion, filters pushed down.

`search()` is the interface tools and evals consume; it returns ScoredChunk
with full provenance (section + page anchors are what make citations
verifiable, D7/D9). Fusion is reciprocal rank fusion — 1/(rrf_k + rank),
summed across legs — so no leg weights to tune (D8).

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
finding 3). corpus.db failing is fatal by design: without it there is no
text to return at all.

Rerank (config.rerank_enabled) ships only if evals justify it (D8/#19); the
flag exists, the stage does not yet.

__main__ is the spine checkpoint (#16): `just ask q="..."` prints top-k over
the real corpus; `--bench` measures the p95 the spec §10 Chroma assumption
asks for. The real REPL is #24.
"""

import argparse
import logging
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from askrag import db, telemetry
from askrag.config import Settings, get_settings
from askrag.ingest.embed_chunks import EmbeddingError
from askrag.retrieval import fts
from askrag.retrieval.embeddings import QueryEmbedder
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
class Filters:
    """Metadata filters, pushed down into BOTH legs (D8). None = no filter."""

    category: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    # A scope, not a filter: `None` means unscoped, an EMPTY tuple means
    # nothing is in scope. Set server-side from a landing-page claim, never
    # by the model — see routes_chat's scope handling (§5/§6).
    paper_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ScoredChunk:
    """The retrieval product (issue #16 interface): provenance + fused score.

    `leg` records which side(s) surfaced the chunk: "vector", "bm25", "both".
    """

    chunk_id: str
    paper_id: str
    section: str
    page_start: int
    page_end: int
    text: str
    score: float
    leg: str
    version: str | None  # papers.version — the D9 pinned-PDF anchor


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


class QueryEmbedderLike(Protocol):
    """The embedder seam HybridSearch depends on (tests inject fakes)."""

    def embed_query(self, text: str) -> list[float]: ...


class VectorStoreLike(Protocol):
    """The store seam — also what a pgvector implementation must satisfy (D4)."""

    def query(
        self,
        embedding: list[float],
        k: int,
        *,
        category: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        paper_ids: tuple[str, ...] | None = None,
    ) -> list[str]: ...


class HybridSearch:
    """Both legs + fusion + hydration, holding the process-wide resources."""

    def __init__(
        self,
        settings: Settings,
        embedder: QueryEmbedderLike | None = None,
        vector_store: VectorStoreLike | None = None,
        corpus_db_path: Path | None = None,
    ) -> None:
        # Injectable seams for tests; production loads the real model here —
        # the one-time cold cost the FastAPI lifespan will pay once (#30).
        self._settings = settings
        self._embedder = embedder if embedder is not None else QueryEmbedder(settings)
        self._store = vector_store if vector_store is not None else VectorStore(settings)
        self._corpus_db_path = corpus_db_path  # None -> settings path via db.py

    def search(
        self, query: str, filters: Filters | None = None, k: int | None = None
    ) -> list[ScoredChunk]:
        settings = self._settings
        filters = filters if filters is not None else Filters()
        top_k = k if k is not None else settings.search_top_k
        if not query.strip():
            # A blank query must return nothing, not garbage: the vector leg
            # would otherwise embed the bare task prefix and return whatever
            # sits near it (observed live before this guard existed).
            return []
        if settings.rerank_enabled:
            raise NotImplementedError("rerank ships only if evals justify it (D8, decided in #19)")
        tracer = telemetry.get_tracer("askrag.retrieval")
        with tracer.start_as_current_span("askrag.retrieval.search") as span:
            span.set_attribute("askrag.model_slug", settings.embedding_model_slug)
            span.set_attribute("askrag.k", top_k)

            legs: dict[str, list[str]] = {}
            try:
                embedding = self._embedder.embed_query(query)
                legs["vector"] = self._store.query(
                    embedding,
                    top_k,
                    category=filters.category,
                    year_min=filters.year_min,
                    year_max=filters.year_max,
                    paper_ids=filters.paper_ids,
                )
            except _VECTOR_LEG_OPERATIONAL_ERRORS:
                # Fail-soft BY DESIGN (D8): a dead vector leg degrades to
                # BM25-only, never a dead site. corpus.db errors below stay
                # fatal — without it there is nothing to return. Narrowed to
                # the operational error set (finding 3): a code bug now
                # propagates instead of silently degrading.
                _log.warning("vector leg failed; degrading to BM25-only (D8)", exc_info=True)
                span.set_attribute("askrag.degraded", True)

            conn = db.connect_corpus(self._corpus_db_path)
            try:
                with tracer.start_as_current_span("askrag.retrieval.bm25"):
                    legs["bm25"] = fts.search_bm25(
                        conn,
                        query,
                        top_k,
                        category=filters.category,
                        year_min=filters.year_min,
                        year_max=filters.year_max,
                        paper_ids=filters.paper_ids,
                    )
                fused = rrf_fuse(legs, settings.rrf_k)
                ranked = sorted(fused.items(), key=lambda kv: kv[1][0], reverse=True)[:top_k]
                results = self._hydrate(conn, ranked)
            finally:
                conn.close()

            span.set_attribute("askrag.results", len(results))
            for leg_name, ids in legs.items():
                span.set_attribute(f"askrag.leg.{leg_name}", len(ids))
        return results

    def _hydrate(
        self,
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
                f"SELECT c.chunk_id, c.paper_id, c.section, c.page_start, c.page_end,"
                f"       c.text, p.version FROM chunks c"
                f" JOIN papers p ON p.arxiv_id = c.paper_id"
                f" WHERE c.chunk_id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        return [
            ScoredChunk(
                chunk_id=chunk_id,
                paper_id=rows[chunk_id]["paper_id"],
                section=rows[chunk_id]["section"],
                page_start=rows[chunk_id]["page_start"],
                page_end=rows[chunk_id]["page_end"],
                text=rows[chunk_id]["text"],
                score=score,
                leg=leg,
                version=rows[chunk_id]["version"],
            )
            for chunk_id, (score, leg) in ranked
        ]


# --- spine checkpoint CLI (#16); the real REPL is #24 -------------------------

_BENCH_QUERIES = [
    # Mixed shapes: natural-language, exact-match acronyms, names, filters' load
    "chain of thought prompting",
    "hallucination detection methods",
    "graph neural network scalability",
    "RLHF reward model overoptimization",
    "BLEU score machine translation evaluation",
    "transformer attention memory efficiency",
    "quantized feedback fading channel capacity",
    "convex optimization convergence rate",
    "self-supervised speech representation",
    "retrieval augmented generation citations",
]


def _print_results(results: list[ScoredChunk]) -> None:
    for r in results:
        version = r.version or "v?"
        pages = f"p{r.page_start}" + (f"-{r.page_end}" if r.page_end != r.page_start else "")
        text = " ".join(r.text.split())[:100]
        print(f"{r.paper_id} {version} | {r.section[:40]} | {pages} | {r.score:.4f} | {text}")


def _bench(searcher: HybridSearch, k: int) -> None:
    # 100 mixed queries (spec §10: embedded-Chroma latency assumption).
    queries = (_BENCH_QUERIES * 10)[:100]
    times: list[float] = []
    for q in queries:
        start = time.perf_counter()
        searcher.search(q, k=k)
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    p50 = statistics.median(times)
    p95 = times[int(len(times) * 0.95) - 1]
    print(
        f"bench: {len(times)} queries, k={k}: p50 {p50:.1f} ms, p95 {p95:.1f} ms, "
        f"max {times[-1]:.1f} ms (warm process; cold model load reported separately)"
    )


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("query", nargs="?", default=None, help="query text")
    parser.add_argument("-k", type=int, default=None, help="top-k (default: config)")
    parser.add_argument("--category", default=None, help="primary category, e.g. cs.CL")
    parser.add_argument("--year-min", type=int, default=None)
    parser.add_argument("--year-max", type=int, default=None)
    parser.add_argument("--bench", action="store_true", help="p95 over 100 mixed queries (§10)")
    args = parser.parse_args(argv)
    if not args.bench and args.query is None:
        parser.error("a query is required unless --bench")
    try:
        cold_start = time.perf_counter()
        searcher = HybridSearch(settings)
        cold_ms = (time.perf_counter() - cold_start) * 1000
        print(f"model+store cold load: {cold_ms:.0f} ms", file=sys.stderr)
        if args.bench:
            _bench(searcher, args.k or settings.search_top_k)
        else:
            filters = Filters(
                category=args.category, year_min=args.year_min, year_max=args.year_max
            )
            _print_results(searcher.search(args.query, filters=filters, k=args.k))
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
