"""`just ask q="..."`: top-k hybrid search over one source's index (#16, D21).

The retrieval spine's checkpoint, for any source: `--source` picks the index
(default arxiv), `--facet key=value`, `--day-min` and `--day-max` filter it,
and `--bench` measures the p95 the spec §10 Chroma assumption asks for.
"""

import argparse
import statistics
import sys
import time

from askrag import telemetry
from askrag.config import get_settings
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import HybridSearch, ScoredChunk
from askrag.sources.source_specs import SOURCES

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
        version = r.version or "-"
        span = f"@{r.pos_start}" + (f"-{r.pos_end}" if r.pos_end != r.pos_start else "")
        text = " ".join(r.text.split())[:100]
        print(f"{r.doc_id} {version} | {r.section[:40]} | {span} | {r.score:.4f} | {text}")


def _bench(searcher: HybridSearch, k: int) -> None:
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


def _facet(text: str) -> tuple[str, str]:
    key, sep, value = text.partition("=")
    if not sep or not value:
        raise argparse.ArgumentTypeError(f"facet {text!r} is not key=value")
    return key, value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("query", nargs="?", default=None, help="query text")
    parser.add_argument("--source", choices=sorted(SOURCES), default="arxiv")
    parser.add_argument("-k", type=int, default=None, help="top-k (default: config)")
    parser.add_argument("--facet", type=_facet, action="append", default=[], help="key=value")
    parser.add_argument("--day-min", type=int, default=None, help="YYYYMMDD, inclusive")
    parser.add_argument("--day-max", type=int, default=None, help="YYYYMMDD, inclusive")
    parser.add_argument("--bench", action="store_true", help="p95 over 100 mixed queries (§10)")
    args = parser.parse_args(argv)
    if not args.bench and args.query is None:
        parser.error("a query is required unless --bench")
    source = SOURCES[args.source]
    settings = source.search_settings(get_settings())
    telemetry.init(settings)
    try:
        cold_start = time.perf_counter()
        searcher = HybridSearch(settings, source.index(settings))
        cold_ms = (time.perf_counter() - cold_start) * 1000
        print(f"model+store cold load: {cold_ms:.0f} ms", file=sys.stderr)
        if args.bench:
            _bench(searcher, args.k or settings.search_top_k)
        else:
            filters = Filters(day_min=args.day_min, day_max=args.day_max, facets=tuple(args.facet))
            _print_results(searcher.search(args.query, filters=filters, k=args.k))
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
