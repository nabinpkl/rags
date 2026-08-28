"""citations.tsv -> corpus/frontier.json — which papers the agent must be able to read.

THE MANIFEST. This file is the one place the landing page's scope is defined,
and it inverts the usual dependency: instead of indexing a corpus and building a
page over whatever got indexed, the page's claims name the papers to index.

Every foundation the page ranks, and a bounded sample of the citers behind each,
gets chunked and embedded. Nothing else does. That makes "every link on the page
is answerable" a property of construction rather than of coverage — a stronger
guarantee than "most of the corpus is indexed", and a far cheaper one: 272
papers instead of 18,844.

The citer sample is taken newest-first, and the page says "8 of 1,174" rather
than implying it lists them all. A defensible rule stated out loud beats an
accident of sort order that a reader cannot see.

Telemetry (D15): askrag.ingest.select_frontier run span with per-stage counts.
"""

import argparse
import collections
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from askrag import db, telemetry
from askrag.config import get_settings
from askrag.ingest.extract_citations import read_citations

_log = logging.getLogger("askrag.ingest.select_frontier")


@dataclass(frozen=True)
class Frontier:
    """The index manifest: what the page claims, and therefore what must be readable."""

    top_cited: int
    citers_per_work: int
    cited_works: list[str]
    citers: dict[str, list[str]]

    @property
    def paper_ids(self) -> list[str]:
        """Every id to chunk and embed — the foundations plus their sampled citers."""
        ids = set(self.cited_works)
        for sample in self.citers.values():
            ids.update(sample)
        return sorted(ids)


def select(edges: list[tuple[str, str]], *, top_cited: int, citers_per_work: int) -> Frontier:
    """Rank cited works by citer count; sample the newest citers of each.

    Ties on citer count break by id, and the citer sample is the highest ids
    first: an arXiv id sorts chronologically within its id-month, so "newest"
    needs no date lookup and cannot disagree with what the page displays.
    """
    citers_by_work: dict[str, list[str]] = collections.defaultdict(list)
    for citing_id, cited_id in edges:
        citers_by_work[cited_id].append(citing_id)

    ranked = sorted(citers_by_work, key=lambda work: (-len(citers_by_work[work]), work))
    cited_works = ranked[:top_cited]
    citers = {
        work: sorted(set(citers_by_work[work]), reverse=True)[:citers_per_work]
        for work in cited_works
    }
    return Frontier(
        top_cited=top_cited,
        citers_per_work=citers_per_work,
        cited_works=cited_works,
        citers=citers,
    )


def run(
    citations_path: Path, frontier_path: Path, *, top_cited: int, citers_per_work: int
) -> Frontier:
    """Derive the manifest from the citation graph and write it."""
    tracer = telemetry.get_tracer("askrag.ingest")
    with tracer.start_as_current_span("askrag.ingest.select_frontier") as span:
        frontier = select(
            read_citations(citations_path),
            top_cited=top_cited,
            citers_per_work=citers_per_work,
        )
        tmp = frontier_path.with_suffix(frontier_path.suffix + ".tmp")
        frontier_path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(
                {
                    # The rule travels with its result: a reader of this file
                    # can tell what produced the list without reading the code.
                    "rule": {
                        "top_cited": frontier.top_cited,
                        "citers_per_work": frontier.citers_per_work,
                        "citer_order": "newest first, by arxiv_id descending",
                    },
                    "cited_works": frontier.cited_works,
                    "citers": frontier.citers,
                    "paper_ids": frontier.paper_ids,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        tmp.replace(frontier_path)

        span.set_attribute("askrag.cited_works", len(frontier.cited_works))
        span.set_attribute("askrag.paper_ids", len(frontier.paper_ids))

    _log.info(
        f"select_frontier: top {len(frontier.cited_works)} cited works + up to "
        f"{citers_per_work} citers each -> {len(frontier.paper_ids)} papers to index"
    )
    return frontier


def unanswerable_ids(conn: sqlite3.Connection, frontier: Frontier) -> list[str]:
    """Manifest ids with no `chunks` rows — i.e. links the page cannot answer.

    This is THE invariant the whole inversion buys: the page names a paper, so
    the agent must be able to read it. An empty list is the shippable state;
    anything else means the index run did not cover the manifest, and the
    matching links would dead-end for a visitor.
    """
    ids = frontier.paper_ids
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    indexed = {
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT paper_id FROM chunks WHERE paper_id IN ({placeholders})", ids
        )
    }
    return [arxiv_id for arxiv_id in ids if arxiv_id not in indexed]


class FrontierError(Exception):
    """The manifest is missing or unreadable."""


def read_frontier(frontier_path: Path) -> Frontier:
    """The manifest as written — the reader every consumer of the scope uses."""
    if not frontier_path.exists():
        raise FrontierError(
            f"no index manifest at {frontier_path} — run `just frontier` "
            "(select_frontier) before anything that scopes to it"
        )
    record = json.loads(frontier_path.read_text(encoding="utf-8"))
    return Frontier(
        top_cited=record["rule"]["top_cited"],
        citers_per_work=record["rule"]["citers_per_work"],
        cited_works=record["cited_works"],
        citers=record["citers"],
    )


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check every manifest paper is indexed in corpus.db; do not rewrite the manifest",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify:
            frontier = read_frontier(settings.frontier_path)
            conn = db.connect_corpus(settings.corpus_db_path)
            try:
                missing = unanswerable_ids(conn, frontier)
            finally:
                conn.close()
            if missing:
                _log.error(
                    f"{len(missing)} of {len(frontier.paper_ids)} manifest papers are NOT "
                    f"indexed — those links dead-end (first: {missing[0]})"
                )
                return 1
            _log.info(
                f"verify: all {len(frontier.paper_ids)} manifest papers are indexed — "
                "every link on the page is answerable"
            )
            return 0
        run(
            citations_path=settings.citations_path,
            frontier_path=settings.frontier_path,
            top_cited=settings.frontier_top_cited,
            citers_per_work=settings.frontier_citers_per_work,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
