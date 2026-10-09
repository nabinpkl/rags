"""Facet counting over corpus.db `papers`, and the one definition of
"indexed" (D-2, issue #27; D16, issue #73).

`count_scalar`/`count_grouped` back `query_metadata`'s `count_papers`: one
`{Literal -> column}` map, one WHERE-builder, one GROUP BY template, with
`max_groups` a parameter rather than a second copy of the query. The explorer
facet rail and `GET /api/facets` that once shared them were removed with
`/app` (2026-09-30).

`where_clause` always applies `INDEXED_PREDICATE`: a paper with no `chunks`
rows is one the agent can never retrieve or search, so no count it reports
may include it. This is an always-on scope, not a `CountFilters` field: it
has no "off" state a caller can request. The predicate is also imported
directly by the catalog's indexed holding, the landing routes and
`drive_ui`'s target checks.
"""

import sqlite3
from dataclasses import dataclass

# group_by name -> the real papers column it resolves to. Callers only ever
# supply the name; this map is the only place a column name reaches SQL
# (mirrors query_metadata's pre-existing contract: no string interpolation
# of a caller-controlled column name, §6).
GROUP_BY_COLUMNS = {
    "category": "primary_category",
    "year": "year",
    "license": "license",
    "venue": "venue",
}

# The single definition of "indexed" (D16, issue #73) — a paper the app can
# actually search/read. Import it; never copy-paste this predicate.
INDEXED_PREDICATE = "EXISTS (SELECT 1 FROM chunks c WHERE c.paper_id = papers.arxiv_id)"


@dataclass(frozen=True)
class CountFilters:
    """`papers` predicates pushed into the WHERE clause. None = no filter."""

    category: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    has_license: bool | None = None


@dataclass(frozen=True)
class FacetBucket:
    value: str | int | None
    count: int


def where_clause(filters: CountFilters) -> tuple[str, list[object]]:
    clauses: list[str] = [INDEXED_PREDICATE]
    params: list[object] = []
    if filters.category is not None:
        clauses.append("primary_category = ?")
        params.append(filters.category)
    if filters.year_min is not None:
        clauses.append("year >= ?")
        params.append(filters.year_min)
    if filters.year_max is not None:
        clauses.append("year <= ?")
        params.append(filters.year_max)
    if filters.has_license is not None:
        clauses.append("license IS NOT NULL" if filters.has_license else "license IS NULL")
    where = f" WHERE {' AND '.join(clauses)}"
    return where, params


def count_scalar(conn: sqlite3.Connection, filters: CountFilters) -> int:
    where, params = where_clause(filters)
    row = conn.execute(f"SELECT COUNT(*) FROM papers{where}", params).fetchone()
    return row[0]


def count_grouped(
    conn: sqlite3.Connection,
    group_by: str,  # a GROUP_BY_COLUMNS key
    filters: CountFilters,
    max_groups: int,
) -> tuple[tuple[FacetBucket, ...], bool]:
    """Distinct-value counts for one dimension, highest count first.

    Returns (buckets, truncated) — `truncated` is True when more distinct
    groups exist than `max_groups` allowed through (one extra row is
    fetched to detect this without a second COUNT(DISTINCT ...) query).
    """
    column = GROUP_BY_COLUMNS[group_by]
    where, params = where_clause(filters)
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) FROM papers{where} "
        f"GROUP BY {column} ORDER BY COUNT(*) DESC LIMIT ?",
        [*params, max_groups + 1],
    ).fetchall()
    truncated = len(rows) > max_groups
    buckets = tuple(FacetBucket(value=r[0], count=r[1]) for r in rows[:max_groups])
    return buckets, truncated
