"""Retrieval evals over the golden set (D14, #18): `just eval`.

Scores keyword-only (BM25), semantic-only (vector) and hybrid (RRF) retrieval
on every counted golden record: chunk recall@k, MRR, and paper recall@k.
Paper recall sits beside chunk recall because the set does not check that
its expected chunk is the ONLY one answering a question (D14 amendment
2026-09-30), so chunk recall understates where a paper repeats itself.

The legs are called directly rather than through `HybridSearch.search`: that
path degrades to BM25-only when the vector leg fails (D8), which on a live
site is the point and in an eval would quietly report a keyword run as
hybrid. Here a vector failure raises. Fusion is the same `rrf_fuse`.

Rerank has no row: the stage is not built (D8 makes it eval-gated, #19).
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
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

# question -> {config: rank-ordered chunk ids}
Retriever = Callable[[str], dict[str, list[str]]]


def paper_of(chunk_id: str) -> str:
    return chunk_id.split("#", 1)[0]


def recall_at(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Share of the expected chunks inside the top k (a multi_hop record
    with two expected chunks scores 0.5 for finding one)."""
    top = set(ranked[:k])
    return sum(1 for c in expected if c in top) / len(expected)


def reciprocal_rank(ranked: Sequence[str], expected: Sequence[str]) -> float:
    """1 / rank of the first expected chunk, 0 if none was retrieved."""
    wanted = set(expected)
    for rank, chunk_id in enumerate(ranked, start=1):
        if chunk_id in wanted:
            return 1.0 / rank
    return 0.0


def paper_recall_at(ranked: Sequence[str], paper_id: str, k: int) -> float:
    return 1.0 if any(paper_of(c) == paper_id for c in ranked[:k]) else 0.0


@dataclass(frozen=True)
class Scores:
    n: int
    recall: dict[int, float]
    mrr: float
    paper_recall: dict[int, float]


def score(
    records: Sequence[GoldenRecord],
    rankings: dict[str, dict[str, list[str]]],
    config: str,
    ks: Sequence[int],
) -> Scores:
    """Mean of each metric over `records`, for one config. `rankings` is
    keyed by record id."""
    if not records:
        raise ValueError("no records to score")
    n = len(records)
    ranked = {r.id: rankings[r.id][config] for r in records}
    return Scores(
        n=n,
        recall={
            k: sum(recall_at(ranked[r.id], r.expected_chunk_ids, k) for r in records) / n
            for k in ks
        },
        mrr=sum(reciprocal_rank(ranked[r.id], r.expected_chunk_ids) for r in records) / n,
        paper_recall={
            k: sum(paper_recall_at(ranked[r.id], r.expected_paper_id, k) for r in records) / n
            for k in ks
        },
    )


def make_retriever(settings: Settings, conn: sqlite3.Connection, depth: int) -> Retriever:
    embedder = QueryEmbedder(settings)
    store = VectorStore(settings)

    def retrieve(question: str) -> dict[str, list[str]]:
        legs = {
            "bm25": fts.search_bm25(conn, question, depth),
            "vector": store.query(embedder.embed_query(question), depth),
        }
        fused = rrf_fuse(legs, settings.rrf_k)
        hybrid = sorted(fused, key=lambda c: fused[c][0], reverse=True)[:depth]
        return {**legs, "hybrid": hybrid}

    return retrieve


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
        "ks": list(settings.eval_recall_ks),
    }
    blob = json.dumps(inputs, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def render(
    records: Sequence[GoldenRecord],
    rankings: dict[str, dict[str, list[str]]],
    ks: Sequence[int],
    *,
    n_papers: int,
    n_chunks: int,
    run_id: str,
) -> str:
    k_lo = min(ks)
    head = (
        "| Retrieval | "
        + " | ".join(f"Recall@{k}" for k in ks)
        + " | MRR | "
        + " | ".join(f"Paper recall@{k}" for k in ks)
        + " |"
    )
    lines = [
        f"{len(records)} golden questions, model-checked rather than human-verified"
        " (D14 amendment 2026-09-30), over"
        f" {n_papers:,} indexed papers and {n_chunks:,} chunks. Run `{run_id}`.",
        "",
        head,
        "|" + "---|" * (2 + 2 * len(ks)),
    ]
    for config, label in CONFIGS.items():
        s = score(records, rankings, config, ks)
        lines.append(
            f"| {label} | "
            + " | ".join(_pct(s.recall[k]) for k in ks)
            + f" | {s.mrr:.2f} | "
            + " | ".join(_pct(s.paper_recall[k]) for k in ks)
            + " |"
        )

    types = [t for t in GoldenType if any(r.type == t for r in records)]
    lines += [
        "",
        f"Recall@{k_lo} by question type:",
        "",
        "| Question type | n | " + " | ".join(CONFIGS.values()) + " |",
        "|" + "---|" * (2 + len(CONFIGS)),
    ]
    for t in types:
        subset = [r for r in records if r.type == t]
        cells = [_pct(score(subset, rankings, c, ks).recall[k_lo]) for c in CONFIGS]
        lines.append(f"| {t.value} | {len(subset)} | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"One question is {100 / len(records):.1f} points at this size, so gaps"
        " under about 5 points are noise.",
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
    ks = sorted(settings.eval_recall_ks)
    records = load_golden(GOLDEN_PATH)

    conn = db.connect_corpus(None)
    try:
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        n_papers = conn.execute("SELECT count(DISTINCT paper_id) FROM chunks").fetchone()[0]
        retrieve = make_retriever(settings, conn, max(ks))
        rankings: dict[str, dict[str, list[str]]] = {}
        for i, r in enumerate(records, start=1):
            rankings[r.id] = retrieve(r.question)
            print(f"\r{i}/{len(records)}", end="", file=sys.stderr, flush=True)
        print(file=sys.stderr)
    finally:
        conn.close()

    run_id = fingerprint(settings, GOLDEN_PATH, n_chunks)
    table = render(records, rankings, ks, n_papers=n_papers, n_chunks=n_chunks, run_id=run_id)
    print(table, end="")
    if args.write_readme:
        README_PATH.write_text(splice_readme(README_PATH.read_text(), table))
        print(f"wrote {README_PATH.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
