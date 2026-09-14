"""citations.tsv + archive.zip -> corpus/cited_works.jsonl — who we are citing.

The landing page ranks the works our recent cohort cites, and 98% of them are
outside the cohort: we hold no text, no PDF, and no `papers` row for Qwen3 or
PPO. Their title, authors, category, and version come from the Kaggle catalog
instead, at zero download cost — the whole reason the page can name a foundation
it has never fetched.

This is an INPUT to build_indexes.py, not a writer into corpus.db (same contract
as extract_citations.py: corpus.db is drop-and-rebuilt from its inputs).

Not every cited id resolves. Ids the catalog snapshot predates, or that were
withdrawn, are reported as a count and written with a null title rather than
dropped — a citation to an unresolvable work is still a citation, and dropping
it would quietly shrink every count on the page.

Telemetry (D15): askrag.ingest.resolve_cited_works run span with per-stage counts.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from askrag import telemetry
from askrag.config import get_settings
from askrag.ingest import kaggle_seed
from askrag.ingest.extract_citations import read_citations
from askrag.ingest.latex_text import latex_to_text

_log = logging.getLogger("askrag.ingest.resolve_cited_works")


@dataclass(frozen=True)
class CitedWorkRow:
    """One `cited_works` row: catalog metadata for a work we cite.

    Deliberately NOT a `PaperRow`. A `papers` row means "we hold this paper's
    text" and carries the five diversity facets and a license; a cited work is
    catalog metadata for something we may never hold, and conflating the two
    would let a paper we cannot read appear anywhere a readable one can.
    """

    arxiv_id: str
    title: str | None
    authors: str | None
    primary_category: str | None
    year: int | None
    version: str | None

    @property
    def resolved(self) -> bool:
        return self.title is not None


@dataclass
class ResolveStats:
    distinct_cited: int = 0
    resolved: int = 0
    unresolved: int = 0


def _normalize(value: str | None) -> str | None:
    """Catalog titles and author lists wrap across lines; collapse the wrapping."""
    return " ".join(value.split()) if value else None


def _to_row(arxiv_id: str, record: dict[str, Any]) -> CitedWorkRow:
    categories = str(record.get("categories") or "")
    return CitedWorkRow(
        arxiv_id=arxiv_id,
        title=_normalize(record.get("title")),
        authors=_normalize(record.get("authors")),
        primary_category=categories.split()[0] if categories else None,
        year=kaggle_seed.first_version_year(record),
        version=kaggle_seed.latest_version(record),
    )


def run(citations_path: Path, seed_zip: Path, cited_works_path: Path) -> ResolveStats:
    """Resolve every distinct cited id against the catalog, resolvable or not."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = ResolveStats()
    with tracer.start_as_current_span("askrag.ingest.resolve_cited_works") as span:
        wanted = {cited_id for _, cited_id in read_citations(citations_path)}
        stats.distinct_cited = len(wanted)

        rows: dict[str, CitedWorkRow] = {
            record["id"]: _to_row(record["id"], record)
            for record in kaggle_seed.iter_records(seed_zip, wanted)
        }
        stats.resolved = len(rows)
        # Unresolvable ids are written with null metadata, not dropped: the edge
        # that named them is real, and a silently shorter table would understate
        # every count derived from it.
        for arxiv_id in sorted(wanted - rows.keys()):
            rows[arxiv_id] = CitedWorkRow(arxiv_id, None, None, None, None, None)
        stats.unresolved = stats.distinct_cited - stats.resolved

        tmp = cited_works_path.with_suffix(cited_works_path.suffix + ".tmp")
        cited_works_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as handle:
            for arxiv_id in sorted(rows):
                row = rows[arxiv_id]
                handle.write(
                    json.dumps(
                        {
                            "arxiv_id": row.arxiv_id,
                            "title": row.title,
                            "authors": row.authors,
                            "primary_category": row.primary_category,
                            "year": row.year,
                            "version": row.version,
                        }
                    )
                    + "\n"
                )
        tmp.replace(cited_works_path)

        span.set_attribute("askrag.distinct_cited", stats.distinct_cited)
        span.set_attribute("askrag.resolved", stats.resolved)
        span.set_attribute("askrag.unresolved", stats.unresolved)

    share = stats.resolved / stats.distinct_cited if stats.distinct_cited else 0.0
    _log.info(
        f"resolve_cited_works: {stats.distinct_cited} distinct cited works, "
        f"{stats.resolved} resolved ({share:.1%}), {stats.unresolved} unresolved "
        f"-> {cited_works_path.name}"
    )
    return stats


def _clean(value: str | None) -> str | None:
    return latex_to_text(value) if value else value


def read_cited_works(cited_works_path: Path) -> list[CitedWorkRow]:
    """The resolved catalog rows — the reader build_indexes uses."""
    rows: list[CitedWorkRow] = []
    for line in cited_works_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        rows.append(
            CitedWorkRow(
                arxiv_id=record["arxiv_id"],
                # Same boundary as papers (build_indexes._read_papers): the
                # resolved jsonl keeps the catalog's own LaTeX, corpus.db
                # gets the text a reader sees.
                title=_clean(record["title"]),
                authors=_clean(record["authors"]),
                primary_category=record["primary_category"],
                year=record["year"],
                version=record["version"],
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    try:
        run(
            citations_path=settings.citations_path,
            seed_zip=settings.kaggle_seed_path,
            cited_works_path=settings.cited_works_path,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
