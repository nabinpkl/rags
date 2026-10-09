"""corpus/text/{YYMM}/{arxiv_id}.txt -> corpus/citations.tsv — the citation graph.

Every number on the landing page is a count over this file: which papers our
recent cohort cites, and how often. It is an INPUT to build_indexes.py (like
chunks.jsonl), not a writer into corpus.db — corpus.db is drop-and-rebuilt from
its inputs, so a stage that wrote into it directly would be erased by the next
build.

Scope: **new-style arXiv ids only** (`YYMM.NNNNN`, April 2007 onward). Old-style
ids (`cs/0701001`) are silently absent from the graph, not silently miscounted;
they are a vanishing share of what a 2026 cohort cites, and the Kaggle catalog
keys them differently. Stated here because a reader counting edges would
otherwise have no way to know.

Bounds are derived, not configured: `_FIRST_ID_MONTH` is the floor, the newest
id-month in the corpus is the ceiling, and the month must be 01-12. That last
check is what keeps a YEAR followed by a number ("..., 2023. 00092") out of the
graph — without it the bare-id form invents hundreds of citations. Nothing here
goes stale when another month is pulled.

Telemetry (D15): askrag.ingest.extract_citations run span with per-stage counts.
"""

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from askrag import telemetry
from askrag.config import get_settings

_log = logging.getLogger("askrag.ingest.extract_citations")

# Protocol facts, not tunables. 0704 is the first new-style arXiv id-month.
_FIRST_ID_MONTH = "0704"

# A reference carrying an explicit arXiv marker: "arXiv:2505.09388",
# "arxiv.org/abs/2505.09388", "https://arxiv.org/pdf/2505.09388v2", "abs/…".
#
# `re.I` is load-bearing and has a regression test: the canonical spelling is
# "arXiv:" with a capital X, and a case-sensitive pattern silently drops roughly
# two thirds of all references while still returning a plausible-looking number.
# `\s*` between the parts tolerates a reference list wrapped mid-URL by the PDF
# text extractor.
_PREFIXED = re.compile(
    r"(?:arxiv\s*[.:/]?\s*(?:org)?\s*/?\s*(?:abs|pdf)?/?\s*|abs/|pdf/)(\d{4}\.\d{4,5})",
    re.IGNORECASE,
)

# A bare "2505.09388" with no marker. Kept because many bibliography styles drop
# the prefix, and rejected unless it falls inside the plausible id-month window
# — the lookarounds stop it matching inside a decimal or a longer digit run.
#
# The trailing guard rejects a following digit, and a "." only when a digit
# follows it: a sentence-final period ends a great many bibliography entries
# ("Qwen3 Technical Report. 2505.09388. 2025.") and rejecting those would drop
# the whole bare-id form for the most common citation style that uses it.
_BARE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?!\d)(?!\.\d)")


class CitationExtractError(Exception):
    """The extraction inputs are unusable (missing text tree, unreadable file)."""


@dataclass
class CitationStats:
    papers_scanned: int = 0
    papers_with_citations: int = 0
    edges: int = 0
    distinct_cited: int = 0
    unreadable: list[str] = field(default_factory=list)


def _is_plausible_id(candidate: str, *, newest_id_month: str) -> bool:
    """Whether `YYMM.NNNNN` names an arXiv id-month that can actually exist.

    The month check is what separates an id from a YEAR followed by a number:
    "Proceedings of ..., 2023. 00092" and "1688.12609" both match the digit
    shape, and both have an impossible month. Without this the bare-id form
    admits hundreds of citations to works that do not exist.
    """
    month = candidate[2:4]
    return _FIRST_ID_MONTH <= candidate[:4] <= newest_id_month and "01" <= month <= "12"


def cited_ids(text: str, *, citing_id: str, newest_id_month: str) -> set[str]:
    """Every new-style arXiv id `text` cites, excluding `citing_id` itself.

    `newest_id_month` bounds the future, and is the newest month in the CORPUS
    rather than the citing paper's own month: we extract the latest version of
    each PDF, and a July paper revised in September legitimately cites August
    work. Bounding by the citing paper's month would drop those as impossible.
    """
    found = {
        match.group(1)
        for pattern in (_PREFIXED, _BARE)
        for match in pattern.finditer(text)
        if _is_plausible_id(match.group(1), newest_id_month=newest_id_month)
    }
    found.discard(citing_id)
    return found


def _text_files(text_dir: Path) -> list[Path]:
    """Every extracted-text file, in a stable order so the output is diffable."""
    if not text_dir.is_dir():
        raise CitationExtractError(f"no extracted-text tree at {text_dir}")
    return sorted(text_dir.glob("*/*.txt"))


def newest_id_month(paths: Sequence[Path]) -> str:
    """The newest id-month we hold — the ceiling on what a reference can name.

    Derived from the corpus rather than configured, so it cannot go stale: pull
    another month and the ceiling rises with it, with nothing to remember to
    update.
    """
    return max((path.stem[:4] for path in paths), default=_FIRST_ID_MONTH)


def run(text_dir: Path, citations_path: Path) -> CitationStats:
    """Walk the extracted text and write the (citing_id, cited_id) edge list."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = CitationStats()
    with tracer.start_as_current_span("askrag.ingest.extract_citations") as span:
        paths = _text_files(text_dir)
        ceiling = newest_id_month(paths)
        edges: list[tuple[str, str]] = []
        distinct: set[str] = set()
        for path in paths:
            citing_id = path.stem
            stats.papers_scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                # One unreadable file must not lose the other 18,843; the count
                # is reported so a silent shortfall can't pass as a real one.
                _log.warning(f"unreadable: {path.name}: {exc}")
                stats.unreadable.append(citing_id)
                continue
            targets = cited_ids(text, citing_id=citing_id, newest_id_month=ceiling)
            if targets:
                stats.papers_with_citations += 1
                distinct |= targets
                edges.extend((citing_id, target) for target in sorted(targets))
        stats.edges = len(edges)
        stats.distinct_cited = len(distinct)

        # tmp + rename: a killed run never leaves a truncated edge list that the
        # next stage would silently treat as the whole graph.
        tmp = citations_path.with_suffix(citations_path.suffix + ".tmp")
        citations_path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("".join(f"{a}\t{b}\n" for a, b in edges), encoding="utf-8")
        tmp.replace(citations_path)

        span.set_attribute("askrag.newest_id_month", ceiling)
        span.set_attribute("askrag.papers_scanned", stats.papers_scanned)
        span.set_attribute("askrag.papers_with_citations", stats.papers_with_citations)
        span.set_attribute("askrag.edges", stats.edges)
        span.set_attribute("askrag.distinct_cited", stats.distinct_cited)
        span.set_attribute("askrag.unreadable", len(stats.unreadable))

    share = stats.papers_with_citations / stats.papers_scanned if stats.papers_scanned else 0.0
    _log.info(
        f"extract_citations: {stats.papers_scanned} papers scanned, "
        f"{stats.papers_with_citations} with references ({share:.1%}), "
        f"{stats.edges} edges -> {stats.distinct_cited} distinct cited works"
        + (f"; {len(stats.unreadable)} unreadable" if stats.unreadable else "")
    )
    return stats


def read_citations(citations_path: Path) -> list[tuple[str, str]]:
    """The edge list as (citing_id, cited_id) pairs — the reader every consumer uses."""
    if not citations_path.exists():
        raise CitationExtractError(
            f"no citation edge list at {citations_path} — run extract_citations first"
        )
    edges: list[tuple[str, str]] = []
    for line in citations_path.read_text(encoding="utf-8").splitlines():
        citing_id, _, cited_id = line.partition("\t")
        if cited_id:
            edges.append((citing_id, cited_id))
    return edges


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    try:
        run(text_dir=settings.text_dir, citations_path=settings.citations_path)
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
