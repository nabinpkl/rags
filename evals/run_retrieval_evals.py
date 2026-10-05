"""Retrieval evals over the golden set (D14, #18): `just eval`.

Scores keyword-only (BM25), semantic-only (vector) and hybrid (RRF) retrieval
on every counted golden record at k = search_top_k, the depth the agent
reads: chunk recall@k, nDCG@k, MRR and paper recall@k, plus per-query
latency. A fourth row runs hybrid over one model rewrite of the question
(rewrite_queries.py), the agent's first move without its loop. Each row also
reports recall at eval_pool_k, retrieved separately with every leg at that
depth: the ceiling for a reranker reordering that pool into the top k.

Paper recall sits beside chunk recall because the set does not check that
its expected chunk is the ONLY one answering a question (D14 amendment
2026-09-30), so chunk recall understates where a paper repeats itself.

The legs are called directly rather than through `HybridSearch.search`: that
path degrades to BM25-only when the vector leg fails (D8), which on a live
site is the point and in an eval would quietly report a keyword run as
hybrid. Here a vector failure raises. Fusion is the same `rrf_fuse` over the
same per-leg depth, and hybrid latency is the sum of its legs because the
live path runs them one after the other.

The rerank row reorders hybrid's top eval_pool_k into the top k with the
pinned cross-encoder (D8 keeps it off the request path until these numbers
justify it); its latency is the pool retrieval plus the rerank, on the build
host's CPU. The rewrite row's latency adds the rewrite call's recorded
seconds.
"""

import argparse
import hashlib
import json
import math
import re
import sqlite3
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from askrag import db
from askrag.config import Settings, get_settings
from askrag.retrieval import fts
from askrag.retrieval.embeddings import QueryEmbedder
from askrag.retrieval.hybrid_search import rrf_fuse
from askrag.retrieval.rerank import Reranked, Reranker
from askrag.retrieval.vector_store import VectorStore

from evals.golden_set import GOLDEN_PATH, GoldenRecord, GoldenType, load_golden
from evals.rewrite_queries import REWRITES_PATH, load_rewrites
from evals.run_store import Retrieved, append_run, load_run, run_path

README_PATH = Path(__file__).parent.parent / "README.md"
_MARKER_START = "<!-- retrieval-evals:start -->"
_MARKER_END = "<!-- retrieval-evals:end -->"

# Row order and labels of the table; the keys are what `retrieve` returns.
CONFIGS: dict[str, str] = {
    "bm25": "Keyword (BM25)",
    "vector": "Semantic (vector)",
    "hybrid": "Hybrid (RRF)",
    "rerank": "Hybrid + rerank",
    "rewrite": "Rewrite + hybrid",
}


def paper_of(chunk_id: str) -> str:
    return chunk_id.split("#", 1)[0]


def recall_at(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Share of the expected chunks inside the top k (a multi_hop record
    with two expected chunks scores 0.5 for finding one)."""
    top = set(ranked[:k])
    return sum(1 for c in expected if c in top) / len(expected)


def ndcg_at(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Binary-relevance nDCG@k, as BEIR and MTEB report retrieval: each
    expected chunk is relevant, gain discounted by log2(rank + 1)."""
    wanted = set(expected)
    dcg = sum(1 / math.log2(i + 2) for i, c in enumerate(ranked[:k]) if c in wanted)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(wanted), k)))
    return dcg / ideal


def reciprocal_rank(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """1 / rank of the first expected chunk in the top k, 0 if none is."""
    wanted = set(expected)
    for rank, chunk_id in enumerate(ranked[:k], start=1):
        if chunk_id in wanted:
            return 1.0 / rank
    return 0.0


def paper_recall_at(ranked: Sequence[str], paper_id: str, k: int) -> float:
    return 1.0 if any(paper_of(c) == paper_id for c in ranked[:k]) else 0.0


@dataclass(frozen=True)
class Scores:
    n: int
    recall: float
    ndcg: float
    mrr: float
    paper_recall: float


def score(
    records: Sequence[GoldenRecord],
    rankings: dict[str, dict[str, list[str]]],
    config: str,
    k: int,
) -> Scores:
    """Mean of each metric at k over `records`, for one config. `rankings`
    is keyed by record id."""
    if not records:
        raise ValueError("no records to score")
    n = len(records)
    ranked = {r.id: rankings[r.id][config] for r in records}

    def mean(metric: Callable[[GoldenRecord], float]) -> float:
        return sum(metric(r) for r in records) / n

    return Scores(
        n=n,
        recall=mean(lambda r: recall_at(ranked[r.id], r.expected_chunk_ids, k)),
        ndcg=mean(lambda r: ndcg_at(ranked[r.id], r.expected_chunk_ids, k)),
        mrr=mean(lambda r: reciprocal_rank(ranked[r.id], r.expected_chunk_ids, k)),
        paper_recall=mean(lambda r: paper_recall_at(ranked[r.id], r.expected_paper_id, k)),
    )


def make_retriever(
    settings: Settings, conn: sqlite3.Connection, k: int, pool_k: int
) -> Callable[[str, str], Retrieved]:
    """`retrieve(question, rewrite)`: the three methods on the question,
    hybrid's pool reranked, and hybrid on the rewrite."""
    embedder = QueryEmbedder(settings)
    store = VectorStore(settings)
    reranker = Reranker(settings)

    def texts(chunk_ids: list[str]) -> list[tuple[str, str]]:
        marks = ",".join("?" * len(chunk_ids))
        rows = dict(
            conn.execute(
                f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({marks})", chunk_ids
            ).fetchall()
        )
        return [(c, rows[c]) for c in chunk_ids]

    def hybrid(query: str, *, rerank: bool = True) -> Retrieved:
        t0 = time.perf_counter()
        bm25 = fts.search_bm25(conn, query, k)
        t1 = time.perf_counter()
        embedding, embed_usd = embedder.embed_query_priced(query)
        if embed_usd is None:
            raise RuntimeError("the embedding reply carried no cost")
        vector = store.query(embedding, k)
        t2 = time.perf_counter()
        fused = rrf_fuse({"bm25": bm25, "vector": vector}, settings.rrf_k)
        top = sorted(fused, key=lambda c: fused[c][0], reverse=True)[:k]
        t3 = time.perf_counter()
        bm25_pool = fts.search_bm25(conn, query, pool_k)
        vector_pool = store.query(embedder.embed_query(query), pool_k)
        fused_pool = rrf_fuse({"bm25": bm25_pool, "vector": vector_pool}, settings.rrf_k)
        top_pool = sorted(fused_pool, key=lambda c: fused_pool[c][0], reverse=True)[:pool_k]
        reranked = reranker.rerank(query, texts(top_pool), pool_k) if rerank else Reranked([], 0.0)
        t5 = time.perf_counter()
        ranked = reranked.chunk_ids
        # One embedding per query, as the live path reuses it; the pool's
        # second embedding call above exists only to time the pool honestly.
        return Retrieved(
            rankings={"bm25": bm25, "vector": vector, "hybrid": top, "rerank": ranked[:k]},
            pools={"bm25": bm25_pool, "vector": vector_pool, "hybrid": top_pool, "rerank": ranked},
            seconds={"bm25": t1 - t0, "vector": t2 - t1, "hybrid": t3 - t0, "rerank": t5 - t3},
            usd={
                "bm25": 0.0,
                "vector": embed_usd,
                "hybrid": embed_usd,
                "rerank": embed_usd + reranked.usd,
            },
        )

    def retrieve(question: str, rewrite: str) -> Retrieved:
        got = hybrid(question)
        rw = hybrid(rewrite, rerank=False)
        return Retrieved(
            rankings={**got.rankings, "rewrite": rw.rankings["hybrid"]},
            pools={**got.pools, "rewrite": rw.pools["hybrid"]},
            seconds={**got.seconds, "rewrite": rw.seconds["hybrid"]},
            usd={**got.usd, "rewrite": rw.usd["hybrid"]},
        )

    return retrieve


def p50_ms(samples: Sequence[float]) -> float:
    return statistics.median(samples) * 1000


def fingerprint(
    settings: Settings, golden_path: Path, n_chunks: int, rewrites_path: Path = REWRITES_PATH
) -> str:
    """Twelve hex characters naming everything a score depends on: the set,
    its rewrites, the index's size, the embedding model and the chunking and
    fusion constants. Two tables with the same fingerprint are comparable."""
    inputs = {
        "golden_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "rewrites_sha256": hashlib.sha256(rewrites_path.read_bytes()).hexdigest(),
        "chunks": n_chunks,
        "embedding": settings.embedding_model_slug,
        "embedding_revision": settings.embedding_model_revision,
        "query_prefix": settings.embedding_query_prefix,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_ratio": settings.chunk_overlap_ratio,
        "chunk_min_tokens": settings.chunk_min_tokens,
        "rrf_k": settings.rrf_k,
        "k": settings.search_top_k,
        "pool_k": settings.eval_pool_k,
        "rerank_backend": settings.rerank_backend,
        "rerank": (
            settings.rerank_openrouter_model
            if settings.rerank_backend == "openrouter"
            else [settings.rerank_model, settings.rerank_model_revision, settings.rerank_max_tokens]
        ),
    }
    blob = json.dumps(inputs, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _usd(value: float) -> str:
    """Dollars, two significant figures in plain decimals; anything under a
    millionth (a query embedding is about $0.00000004) reads as that bound."""
    if value == 0:
        return "$0"
    if value < 1e-6:
        return "<$0.000001"
    return f"${value:.6f}".rstrip("0")


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def render(
    records: Sequence[GoldenRecord],
    rankings: dict[str, dict[str, list[str]]],
    pools: dict[str, dict[str, list[str]]],
    latency_ms: dict[str, float],
    cost_usd: dict[str, float],
    k: int,
    pool_k: int,
    *,
    n_papers: int,
    n_chunks: int,
    run_id: str,
) -> str:
    """Configs ranked by recall@k, best first, then recall@k per type."""
    scores = {c: score(records, rankings, c, k) for c in CONFIGS}
    pool_recall = {c: score(records, pools, c, pool_k).recall for c in CONFIGS}
    ranked = sorted(CONFIGS, key=lambda c: scores[c].recall, reverse=True)
    lines = [
        f"{len(records)} golden questions, model-checked rather than human-verified"
        " (D14 amendment 2026-09-30), over"
        f" {n_papers:,} indexed papers and {n_chunks:,} chunks, scored at the"
        f" top {k} the agent reads. Run `{run_id}`.",
        "",
        f"| Retrieval | Recall@{k} | nDCG@{k} | MRR | Paper recall@{k} | Recall@{pool_k}"
        " | p50 latency | Cost / query |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in ranked:
        s = scores[c]
        lines.append(
            f"| {CONFIGS[c]} | {_pct(s.recall)} | {s.ndcg:.2f} | {s.mrr:.2f}"
            f" | {_pct(s.paper_recall)} | {_pct(pool_recall[c])} | {latency_ms[c]:.0f} ms"
            f" | {_usd(cost_usd[c])} |"
        )

    types = [t for t in GoldenType if any(r.type == t for r in records)]
    lines += [
        "",
        f"Recall@{k} by question type:",
        "",
        "| Question type | n | " + " | ".join(CONFIGS[c] for c in ranked) + " |",
        "|" + "---|" * (2 + len(CONFIGS)),
    ]
    for t in types:
        subset = [r for r in records if r.type == t]
        cells = [_pct(score(subset, rankings, c, k).recall) for c in ranked]
        lines.append(f"| {t.value} | {len(subset)} | " + " | ".join(cells) + " |")
    if GoldenType.VOCABULARY_MISMATCH in types:
        lines += [
            "",
            "vocabulary_mismatch questions may not use any word of their passage that"
            " appears in 500 or fewer chunks, so keyword search can match them only"
            " on common field words.",
        ]
    lines += [
        "",
        f"Recall@{pool_k} is the most a reranker reordering the top {pool_k} into"
        f" the top {k} could reach. Rewrite + hybrid searches one model rewrite of"
        " the question; its latency includes the rewrite call. Hybrid + rerank"
        f" reorders hybrid's top {pool_k} with a cross-encoder on the build host's"
        " CPU; its latency includes retrieving that pool.",
        "",
        f"One question is {100 / len(records):.1f} points at this size, so gaps"
        " under about 5 points are noise. Latency is the median per question on"
        " the build host; the semantic leg includes the embedding API call. Cost is"
        " the mean per question that the providers billed: the embedding, the"
        " rerank and the rewrite call.",
    ]
    return "\n".join(lines) + "\n"


def splice_readme(readme: str, table: str) -> str:
    """Replace the text between the markers; the markers must already exist,
    so a README edit that drops them fails instead of growing a second table."""
    pattern = re.compile(re.escape(_MARKER_START) + r".*?" + re.escape(_MARKER_END), re.S)
    if len(pattern.findall(readme)) != 1:
        raise ValueError(f"README needs exactly one {_MARKER_START} ... {_MARKER_END} block")
    return pattern.sub(lambda _: f"{_MARKER_START}\n{table}{_MARKER_END}", readme)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--write-readme", action="store_true", help="replace the README's results block"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    k, pool_k = settings.search_top_k, settings.eval_pool_k
    records = load_golden(GOLDEN_PATH)
    rewrites = load_rewrites(records)

    conn = db.connect_corpus(None)
    try:
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        n_papers = conn.execute("SELECT count(DISTINCT paper_id) FROM chunks").fetchone()[0]
        run_id = fingerprint(settings, GOLDEN_PATH, n_chunks)
        path = run_path(run_id)
        done = load_run(path)
        todo = [r for r in records if r.id not in done]
        print(f"run {run_id}: {len(done)} questions on file, {len(todo)} to score", file=sys.stderr)
        # Built only when there is work: it loads the reranker.
        retrieve = make_retriever(settings, conn, k, pool_k) if todo else None
        for i, r in enumerate(todo, start=1):
            assert retrieve is not None
            got = retrieve(r.question, rewrites[r.id].rewrite)
            rw = rewrites[r.id]
            done[r.id] = Retrieved(
                got.rankings,
                got.pools,
                {**got.seconds, "rewrite": got.seconds["rewrite"] + rw.seconds},
                {**got.usd, "rewrite": got.usd["rewrite"] + rw.usd},
            )
            append_run(path, r.id, done[r.id])
            print(f"\r{i}/{len(todo)}", end="", file=sys.stderr, flush=True)
        print(file=sys.stderr)
    finally:
        conn.close()

    rankings = {r.id: done[r.id].rankings for r in records}
    pools = {r.id: done[r.id].pools for r in records}
    seconds = {c: [done[r.id].seconds[c] for r in records] for c in CONFIGS}
    latency = {c: p50_ms(seconds[c]) for c in CONFIGS}
    cost = {c: statistics.mean(done[r.id].usd[c] for r in records) for c in CONFIGS}
    table = render(
        records,
        rankings,
        pools,
        latency,
        cost,
        k,
        pool_k,
        n_papers=n_papers,
        n_chunks=n_chunks,
        run_id=run_id,
    )
    print(table, end="")
    if args.write_readme:
        README_PATH.write_text(splice_readme(README_PATH.read_text(), table))
        print(f"wrote {README_PATH.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
