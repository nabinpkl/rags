"""Facet counting over corpus.db `papers` — the shared read helper behind
`query_metadata`'s `count_papers` group-by and `GET /api/facets`/the papers
list's `facets=` scoping (D-2, issue #27 decisions.md entry).

One `{Literal -> column}` map, one WHERE-builder, one GROUP BY query template.
A model-facing histogram (`query_metadata`) and the explorer's facet rail
differ only in how many distinct groups they're allowed to see (`max_groups`
is a parameter, never a second copy of the query) — never in query shape or
which column a group-by name resolves to.
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
    clauses: list[str] = []
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
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
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
