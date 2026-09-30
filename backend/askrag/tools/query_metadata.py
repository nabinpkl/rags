"""tool: query_metadata — enum'd metadata queries over corpus.db (§5).

Replaces model-authored SQL (DECISIONS.md 2026-07-06, pre-#23) with a
`drive_ui`-style discriminated union of exactly three ops: `count_papers`
(scalar count or a group-by histogram), `paper_facets` (point lookup by
paper id), `corpus_stats` (corpus-wide totals). Every op runs a FIXED
parameterized SQL template — filters bind as `?`, and a `group_by` value
resolves through a server-side `{Literal -> column}` map, never a
string-interpolated column name. There is no model-authored SQL path
anywhere, so the SQL-injection/DoS surface the old authorizer/timeout
machinery guarded against no longer exists (§6, superseded).

`count_papers`' group-by counting SQL lives in `askrag.facets` (D-2, issue
#27 DECISIONS.md): one column map and one query template, with the group
cap a parameter — no second copy anywhere.

`count_papers` (via `facets.where_clause`) and `corpus_stats` both scope to
the INDEXED corpus (D16, issue #73): a paper the agent can't actually
retrieve or search must never inflate a total the agent reports back to a
user — `corpus_stats.n_papers` reporting the full `papers` count while
`count_papers` reports the indexed-only count would be the same
silently-diverging-universes bug #73 closed, just moved from the frontend
header into the agent's mouth. `paper_facets` is scoped the same way: an id
with no chunks is refused as unknown, because answering it would give the
agent a title and venue for a paper it cannot read, and the agent's corpus is
the indexed set, not the catalog.

`QueryMetadataArgs` is a `RootModel` over a `Field(discriminator="op")`
union, mirroring `drive_ui.DriveUiArgs`: pydantic picks the matching
per-op model from `op` alone, so each op's JSON schema states exactly its
own fields (a `corpus_stats` call can't also carry `paper_id`).
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from askrag import db
from askrag.config import Settings, get_settings
from askrag.facets import INDEXED_PREDICATE, CountFilters, count_grouped, count_scalar


class QueryMetadataError(Exception):
    """The requested paper id does not exist in corpus.db (§5)."""


class CountPapersArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["count_papers"] = "count_papers"
    category: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    has_license: bool | None = None
    group_by: Literal["category", "year", "license", "venue"] | None = None


class PaperFacetsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["paper_facets"] = "paper_facets"
    paper_id: str = Field(min_length=1)


class CorpusStatsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["corpus_stats"] = "corpus_stats"


_QueryUnion = Annotated[
    CountPapersArgs | PaperFacetsArgs | CorpusStatsArgs, Field(discriminator="op")
]


class QueryMetadataArgs(RootModel[_QueryUnion]):
    """Model-facing input: validates + dispatches on `op` alone."""


@dataclass(frozen=True)
class HistogramBucket:
    value: str | int | None
    count: int


@dataclass(frozen=True)
class CountPapersResult:
    count: int | None  # scalar form (group_by=None)
    histogram: tuple[HistogramBucket, ...] | None  # group_by set; top-N bounded
    truncated: bool  # more distinct groups exist than the top-N cap returned

    def to_model_payload(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "histogram": (
                [{"value": b.value, "count": b.count} for b in self.histogram]
                if self.histogram is not None
                else None
            ),
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class PaperFacetsResult:
    paper_id: str
    title: str
    primary_category: str
    year: int
    version: str | None
    license: str | None
    venue: str | None
    n_chunks: int
    n_pages: int

    def to_model_payload(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "primary_category": self.primary_category,
            "year": self.year,
            "version": self.version,
            "license": self.license,
            "venue": self.venue,
            "n_chunks": self.n_chunks,
            "n_pages": self.n_pages,
        }


@dataclass(frozen=True)
class CorpusStatsResult:
    n_papers: int
    n_chunks: int
    year_min: int | None
    year_max: int | None
    n_categories: int

    def to_model_payload(self) -> dict[str, Any]:
        return {
            "n_papers": self.n_papers,
            "n_chunks": self.n_chunks,
            "year_min": self.year_min,
            "year_max": self.year_max,
            "n_categories": self.n_categories,
        }


def _run_count_papers(
    conn: sqlite3.Connection, args: CountPapersArgs, histogram_max_groups: int
) -> CountPapersResult:
    filters = CountFilters(
        category=args.category,
        year_min=args.year_min,
        year_max=args.year_max,
        has_license=args.has_license,
    )
    if args.group_by is None:
        return CountPapersResult(count=count_scalar(conn, filters), histogram=None, truncated=False)

    buckets, truncated = count_grouped(conn, args.group_by, filters, histogram_max_groups)
    histogram = tuple(HistogramBucket(value=b.value, count=b.count) for b in buckets)
    return CountPapersResult(count=None, histogram=histogram, truncated=truncated)


def _run_paper_facets(conn: sqlite3.Connection, args: PaperFacetsArgs) -> PaperFacetsResult:
    row = conn.execute(
        "SELECT title, primary_category, year, version, license, venue "
        f"FROM papers WHERE arxiv_id = ? AND {INDEXED_PREDICATE}",
        (args.paper_id,),
    ).fetchone()
    if row is None:
        raise QueryMetadataError(f"no indexed paper with id {args.paper_id!r}")

    n_chunks, n_pages = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(page_end), 0) FROM chunks WHERE paper_id = ?",
        (args.paper_id,),
    ).fetchone()
    return PaperFacetsResult(
        paper_id=args.paper_id,
        title=row["title"],
        primary_category=row["primary_category"],
        year=row["year"],
        version=row["version"],
        license=row["license"],
        venue=row["venue"],
        n_chunks=n_chunks,
        n_pages=n_pages,
    )


def _run_corpus_stats(conn: sqlite3.Connection) -> CorpusStatsResult:
    # Scoped to the indexed corpus (D16, issue #73): year_min/year_max/
    # n_categories follow n_papers so the agent never claims year or
    # category coverage from papers it can't actually read.
    n_papers, year_min, year_max, n_categories = conn.execute(
        "SELECT COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT primary_category) "
        f"FROM papers WHERE {INDEXED_PREDICATE}"
    ).fetchone()
    (n_chunks,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return CorpusStatsResult(
        n_papers=n_papers,
        n_chunks=n_chunks,
        year_min=year_min,
        year_max=year_max,
        n_categories=n_categories,
    )


def run(
    args: QueryMetadataArgs,
    *,
    settings: Settings | None = None,
    corpus_db_path: Path | None = None,
) -> CountPapersResult | PaperFacetsResult | CorpusStatsResult:
    settings = settings if settings is not None else get_settings()
    op = args.root
    conn = db.connect_corpus(corpus_db_path)
    try:
        if isinstance(op, CountPapersArgs):
            return _run_count_papers(conn, op, settings.query_metadata_histogram_max_groups)
        if isinstance(op, PaperFacetsArgs):
            return _run_paper_facets(conn, op)
        return _run_corpus_stats(conn)
    finally:
        conn.close()
