"""Publish a finished eval run: `just eval-publish`.

Reads only the committed run file (no retrieval, no model calls) and writes
the README's results block and `frontend/lib/benchmarks/retrieval.json`,
which `/benchmarks` imports
at build time (§4c decision 2 amendment 2026-10-06; DECISIONS.md
2026-10-06). Everything comes from the run file the README table came from,
so the page and the README cannot disagree: the leaderboard with 95%
bootstrap intervals on recall, recall per question type, every question's
rank of its expected passage(s), and hand-picked examples with hybrid's and
the reranker's top 5.

Examples carry paper titles and section names, never passage text (§6c).

The local-reranker row comes from run 492b61d7e3a5, which predates the run
store and kept only totals, so it is pinned here with that run id rather
than read from a file.
"""

import argparse
import json
import random
import re
import sqlite3
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from askrag import db
from askrag.config import Settings, get_settings

from evals.golden_set import GOLDEN_PATH, GoldenRecord, GoldenType, load_golden
from evals.rewrite_queries import REWRITES_PATH, load_rewrites
from evals.run_retrieval_evals import (
    CONFIGS,
    HARDWARE,
    fingerprint,
    p50_ms,
    recall_at,
    report,
    reranker_label,
    score,
)
from evals.run_store import Retrieved, load_run, run_path

EXPORT_PATH = Path(__file__).parent.parent / "frontend" / "lib" / "benchmarks" / "retrieval.json"
README_PATH = Path(__file__).parent.parent / "README.md"
_MARKER_START = "<!-- retrieval-evals:start -->"
_MARKER_END = "<!-- retrieval-evals:end -->"

BOOTSTRAP_RESAMPLES = 4000
BOOTSTRAP_SEED = 20261005
EXAMPLE_DEPTH = 5

# Three the reranker fixed, one it made worse, one nothing finds.
EXAMPLE_QUESTIONS = (
    "what bound on a design matrix guarantees sparse regression works",
    "when can the LME be computed directly",
    "is myopic policy throughput independent of initial belief",
    "which prompting approach handles harmful requests both safely and helpfully",
    "which scene category has the lowest success rate",
)


@dataclass(frozen=True)
class PinnedRow:
    """A leaderboard row from a run that kept only totals."""

    config: str
    run_id: str
    model: str
    recall: float
    ndcg: float
    mrr: float
    paper: float
    pool: float
    p50_ms: float
    usd: float
    by_type: dict[str, float]


LOCAL_RERANK = PinnedRow(
    config="rerank_local",
    run_id="492b61d7e3a5",
    model="Alibaba-NLP/gte-reranker-modernbert-base",
    recall=0.87,
    ndcg=0.71,
    mrr=0.67,
    paper=0.99,
    pool=0.93,
    p50_ms=153433,
    usd=0.0,
    by_type={
        "single_hop": 1.00,
        "exact_match": 1.00,
        "vocabulary_mismatch": 0.82,
        "known_hard": 0.80,
        "multi_hop": 0.70,
    },
)

# Matrix column order: easiest first, two-passage last.
TYPE_ORDER = (
    GoldenType.SINGLE_HOP,
    GoldenType.EXACT_MATCH,
    GoldenType.VOCABULARY_MISMATCH,
    GoldenType.KNOWN_HARD,
    GoldenType.MULTI_HOP,
)

ChunkMeta = Callable[[str], dict[str, str]]


def bootstrap_ci(values: Sequence[float], rng: random.Random) -> tuple[float, float]:
    """95% percentile interval of the mean over resampled questions."""
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return means[int(0.025 * BOOTSTRAP_RESAMPLES)], means[int(0.975 * BOOTSTRAP_RESAMPLES)]


def rank_of(ranked: Sequence[str], chunk_id: str) -> int | None:
    return ranked.index(chunk_id) + 1 if chunk_id in ranked else None


def build(
    records: Sequence[GoldenRecord],
    done: dict[str, Retrieved],
    meta: ChunkMeta,
    *,
    k: int,
    pool_k: int,
    facts: dict[str, object],
    examples: Sequence[str] = EXAMPLE_QUESTIONS,
) -> dict[str, object]:
    """The page's data. Raises when the run lacks a counted question or an
    example question is not in the set: a page over part of a run would
    report numbers no run produced."""
    missing = [r.id for r in records if r.id not in done]
    if missing:
        raise ValueError(f"run file lacks {len(missing)} questions, e.g. {missing[0]}")
    rankings = {r.id: done[r.id].rankings for r in records}
    pools = {r.id: done[r.id].pools for r in records}
    rng = random.Random(BOOTSTRAP_SEED)

    board: list[dict[str, object]] = []
    for c in CONFIGS:
        sc = score(records, rankings, c, k)
        lo, hi = bootstrap_ci(
            [recall_at(rankings[r.id][c], r.expected_chunk_ids, k) for r in records], rng
        )
        board.append(
            {
                "config": c,
                "recall": sc.recall,
                "lo": lo,
                "hi": hi,
                "ndcg": sc.ndcg,
                "mrr": sc.mrr,
                "paper": sc.paper_recall,
                "pool": score(records, pools, c, pool_k).recall,
                "p50_ms": p50_ms([done[r.id].seconds[c] for r in records]),
                "usd": statistics.mean(done[r.id].usd[c] for r in records),
                "run_id": None,
            }
        )
    p = LOCAL_RERANK
    board.append(
        {
            "config": p.config,
            "recall": p.recall,
            "lo": None,
            "hi": None,
            "ndcg": p.ndcg,
            "mrr": p.mrr,
            "paper": p.paper,
            "pool": p.pool,
            "p50_ms": p.p50_ms,
            "usd": p.usd,
            "run_id": p.run_id,
        }
    )
    board.sort(key=lambda b: b["recall"], reverse=True)

    by_type = []
    for t in TYPE_ORDER:
        sub = [r for r in records if r.type == t]
        if not sub:
            continue
        by_type.append(
            {
                "type": t.value,
                "n": len(sub),
                "recall": {
                    **{c: score(sub, rankings, c, k).recall for c in CONFIGS},
                    p.config: p.by_type[t.value],
                },
            }
        )

    queries = sorted(
        (
            {
                "question": r.question,
                "type": r.type.value,
                "rank": {
                    c: [rank_of(rankings[r.id][c], x) for x in r.expected_chunk_ids]
                    for c in CONFIGS
                },
            }
            for r in records
        ),
        key=lambda q: (TYPE_ORDER.index(GoldenType(q["type"])), q["question"].lower()),
    )

    by_question = {r.question: r for r in records}
    absent = [q for q in examples if q not in by_question]
    if absent:
        raise ValueError(f"example question not in the set: {absent[0]!r}")
    shown = []
    for q in examples:
        r = by_question[q]
        expected = r.expected_chunk_ids[0]

        def top(
            config: str, r: GoldenRecord = r, expected: str = expected
        ) -> list[dict[str, object]]:
            return [
                {
                    **meta(c),
                    "grade": 2
                    if c == expected
                    else 1
                    if c.split("#")[0] == r.expected_paper_id
                    else 0,
                }
                for c in rankings[r.id][config][:EXAMPLE_DEPTH]
            ]

        shown.append(
            {
                "question": r.question,
                "type": r.type.value,
                "expected": meta(expected),
                "rank": {c: rank_of(rankings[r.id][c], expected) for c in CONFIGS},
                "hybrid": top("hybrid"),
                "rerank": top("rerank"),
            }
        )

    return {
        **facts,
        "k": k,
        "pool_k": pool_k,
        "n": len(records),
        "board": board,
        "by_type": by_type,
        "queries": queries,
        "examples": shown,
    }


def splice_readme(readme: str, table: str) -> str:
    """Replace the text between the markers; the markers must already exist,
    so a README edit that drops them fails instead of growing a second table."""
    pattern = re.compile(re.escape(_MARKER_START) + r".*?" + re.escape(_MARKER_END), re.S)
    if len(pattern.findall(readme)) != 1:
        raise ValueError(f"README needs exactly one {_MARKER_START} ... {_MARKER_END} block")
    return pattern.sub(lambda _: f"{_MARKER_START}\n{table}{_MARKER_END}", readme)


def chunk_meta(conn: sqlite3.Connection) -> ChunkMeta:
    def meta(chunk_id: str) -> dict[str, str]:
        row = conn.execute(
            "SELECT c.paper_id, c.section, p.title FROM chunks c"
            " JOIN papers p ON p.arxiv_id = c.paper_id WHERE c.chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"chunk {chunk_id} is not in corpus.db")
        paper, section, title = row
        return {
            "id": chunk_id,
            "paper": paper,
            "section": "Title and abstract"
            if section == "__paper__"
            else " ".join(section.split()),
            "title": " ".join(title.split()),
        }

    return meta


def run_facts(
    settings: Settings, records: Sequence[GoldenRecord], conn: sqlite3.Connection
) -> dict[str, object]:
    """What the Method list states, read from where each fact lives."""
    rewrites = load_rewrites(list(records))
    return {
        "exported": date.today().isoformat(),
        "drafted": len(load_golden(GOLDEN_PATH, counted_only=False)),
        "n_papers": conn.execute("SELECT count(DISTINCT paper_id) FROM chunks").fetchone()[0],
        "n_chunks": conn.execute("SELECT count(*) FROM chunks").fetchone()[0],
        "draft_models": sorted({r.draft_model for r in records}),
        "check_models": sorted({r.checks.check_model for r in records}),
        "rewrite_models": sorted({rw.model for rw in rewrites.values()}),
        "embedding_model": settings.embedding_model,
        "embedding_dims": settings.embedding_dims,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_ratio": settings.chunk_overlap_ratio,
        "rrf_k": settings.rrf_k,
        "rerank_model": settings.rerank_openrouter_model,
        "local_rerank_model": LOCAL_RERANK.model,
        "local_rerank_run_id": LOCAL_RERANK.run_id,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "hardware": HARDWARE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    settings = get_settings()
    if settings.rerank_backend != "openrouter":
        raise SystemExit("publish reads the hosted-rerank run; set rerank_backend=openrouter")
    records = load_golden(GOLDEN_PATH)
    conn = db.connect_corpus(None)
    try:
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        run_id = fingerprint(settings, GOLDEN_PATH, n_chunks, REWRITES_PATH)
        done = load_run(run_path(run_id))
        data = build(
            records,
            done,
            chunk_meta(conn),
            k=settings.search_top_k,
            pool_k=settings.eval_pool_k,
            facts={"run_id": run_id, **run_facts(settings, records, conn)},
        )
        # build() has already refused a run missing a question, so the README
        # never gets a table over part of a run either.
        table = report(
            records,
            done,
            settings.search_top_k,
            settings.eval_pool_k,
            n_papers=int(data["n_papers"]),  # ty: ignore[invalid-argument-type]
            n_chunks=n_chunks,
            run_id=run_id,
            reranker=reranker_label(settings),
        )
    finally:
        conn.close()
    README_PATH.write_text(splice_readme(README_PATH.read_text(), table))
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {README_PATH.name} and {EXPORT_PATH.name} from run {run_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
