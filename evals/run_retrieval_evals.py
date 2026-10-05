"""Retrieval evals over the golden set (D14, #18): `just eval`.

Scores keyword-only (BM25), semantic-only (vector) and hybrid (RRF) retrieval
on every counted golden record at k = search_top_k, the depth the agent
reads: chunk recall@k, nDCG@k, MRR and paper recall@k, plus per-query
latency. Paper recall sits beside chunk recall because the set does not
check that its expected chunk is the ONLY one answering a question (D14
amendment 2026-09-30), so chunk recall understates where a paper repeats
itself.

The legs are called directly rather than through `HybridSearch.search`: that
path degrades to BM25-only when the vector leg fails (D8), which on a live
site is the point and in an eval would quietly report a keyword run as
hybrid. Here a vector failure raises. Fusion is the same `rrf_fuse` over the
same per-leg depth, and hybrid latency is the sum of its legs because the
live path runs them one after the other.

Rerank has no row: the stage is not built (D8 makes it eval-gated, #19).
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
from askrag.retrieval.vector_store import VectorStore

from evals.golden_set import GOLDEN_PATH, GoldenRecord, GoldenType, load_golden

README_PATH = Path(__file__).parent.parent / "README.md"
_MARKER_START = "<!-- retrieval-evals:start -->"
_MARKER_END = "<!-- retrieval-evals:end -->"

# Row order and labels of the table; the keys are what `retrieve` returns.
CONFIGS: dict[str, str] = {
    "bm25": "Keyword (BM25)",
    "vector": "Semantic (vector)",
    "hybrid": "Hybrid (RRF)",
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


@dataclass(frozen=True)
class Retrieved:
    """One question's rankings and the seconds each config took."""

    rankings: dict[str, list[str]]
    seconds: dict[str, float]


def make_retriever(
    settings: Settings, conn: sqlite3.Connection, k: int
) -> Callable[[str], Retrieved]:
    embedder = QueryEmbedder(settings)
    store = VectorStore(settings)

    def retrieve(question: str) -> Retrieved:
        t0 = time.perf_counter()
        bm25 = fts.search_bm25(conn, question, k)
        t1 = time.perf_counter()
        vector = store.query(embedder.embed_query(question), k)
        t2 = time.perf_counter()
        fused = rrf_fuse({"bm25": bm25, "vector": vector}, settings.rrf_k)
        hybrid = sorted(fused, key=lambda c: fused[c][0], reverse=True)[:k]
        t3 = time.perf_counter()
        return Retrieved(
            rankings={"bm25": bm25, "vector": vector, "hybrid": hybrid},
            seconds={"bm25": t1 - t0, "vector": t2 - t1, "hybrid": t3 - t0},
        )

    return retrieve


def p50_ms(samples: Sequence[float]) -> float:
    return statistics.median(samples) * 1000


def fingerprint(settings: Settings, golden_path: Path, n_chunks: int) -> str:
    """Twelve hex characters naming everything a score depends on: the set,
    the index's size, the embedding model and the chunking and fusion
    constants. Two tables with the same fingerprint are comparable."""
    inputs = {
        "golden_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "chunks": n_chunks,
        "embedding": settings.embedding_model_slug,
        "embedding_revision": settings.embedding_model_revision,
        "query_prefix": settings.embedding_query_prefix,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_ratio": settings.chunk_overlap_ratio,
        "chunk_min_tokens": settings.chunk_min_tokens,
        "rrf_k": settings.rrf_k,
        "k": settings.search_top_k,
    }
    blob = json.dumps(inputs, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def render(
    records: Sequence[GoldenRecord],
    rankings: dict[str, dict[str, list[str]]],
    latency_ms: dict[str, float],
    k: int,
    *,
    n_papers: int,
    n_chunks: int,
    run_id: str,
) -> str:
    """Configs ranked by recall@k, best first, then recall@k per type."""
    scores = {c: score(records, rankings, c, k) for c in CONFIGS}
    ranked = sorted(CONFIGS, key=lambda c: scores[c].recall, reverse=True)
    lines = [
        f"{len(records)} golden questions, model-checked rather than human-verified"
        " (D14 amendment 2026-09-30), over"
        f" {n_papers:,} indexed papers and {n_chunks:,} chunks, scored at the"
        f" top {k} the agent reads. Run `{run_id}`.",
        "",
        f"| Retrieval | Recall@{k} | nDCG@{k} | MRR | Paper recall@{k} | p50 latency |",
        "|---|---|---|---|---|---|",
    ]
    for c in ranked:
        s = scores[c]
        lines.append(
            f"| {CONFIGS[c]} | {_pct(s.recall)} | {s.ndcg:.2f} | {s.mrr:.2f}"
            f" | {_pct(s.paper_recall)} | {latency_ms[c]:.0f} ms |"
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
        f"One question is {100 / len(records):.1f} points at this size, so gaps"
        " under about 5 points are noise. Latency is the median per question on"
        " the build host; the semantic leg includes the embedding API call.",
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
    k = settings.search_top_k
    records = load_golden(GOLDEN_PATH)

    conn = db.connect_corpus(None)
    try:
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        n_papers = conn.execute("SELECT count(DISTINCT paper_id) FROM chunks").fetchone()[0]
        retrieve = make_retriever(settings, conn, k)
        rankings: dict[str, dict[str, list[str]]] = {}
        seconds: dict[str, list[float]] = {c: [] for c in CONFIGS}
        for i, r in enumerate(records, start=1):
            got = retrieve(r.question)
            rankings[r.id] = got.rankings
            for c in CONFIGS:
                seconds[c].append(got.seconds[c])
            print(f"\r{i}/{len(records)}", end="", file=sys.stderr, flush=True)
        print(file=sys.stderr)
    finally:
        conn.close()

    run_id = fingerprint(settings, GOLDEN_PATH, n_chunks)
    latency = {c: p50_ms(seconds[c]) for c in CONFIGS}
    table = render(
        records, rankings, latency, k, n_papers=n_papers, n_chunks=n_chunks, run_id=run_id
    )
    print(table, end="")
    if args.write_readme:
        README_PATH.write_text(splice_readme(README_PATH.read_text(), table))
        print(f"wrote {README_PATH.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
