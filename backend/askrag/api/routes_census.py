"""GET /api/census/categories, GET /api/census/uptake — what a COMPLETE month says.

Every other landing route describes the corpus: what we hold, what it cites,
what the agent can read. These two describe arXiv, and that is only honest for
a month we hold essentially all of. July and August 2026 are held at 99.95% and
99.99% of the catalog; September at 8%, because the mirror has not published it
yet. So a month enters these panels only above
`landing_census_min_coverage`, and a cohort month that fails it is returned in
`excluded` rather than dropped in silence — "September is missing because we do
not have it" is a fact the page should print, not hide.

D16 is unchanged. These are counts, and counts are honest totals; the lists name
cited works, and opening one lands on the foundation detail, whose citer list is
indexed-only. §6c: metadata and counts, no chunk text.
"""

import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from askrag import db
from askrag.api.routes_landing import (
    Foundation,
    MonthBucket,
    cohort_months,
    month_coverage,
    trim_authors,
)
from askrag.category_names import category_name
from askrag.config import Settings, get_settings

router = APIRouter()


class CategoryShare(BaseModel):
    category: str  # arXiv primary category, e.g. "cs.CV"
    papers: int


class CensusMonth(BaseModel):
    """One complete month, by the primary category arXiv filed each paper under."""

    month: str  # id-month, e.g. "2607"
    papers: int
    catalog_papers: int
    categories: list[CategoryShare]
    # Everything outside the shared top list, so the shares sum to the month.
    other: int


class ExcludedMonth(BaseModel):
    """A cohort month held too thinly to describe arXiv with, and by how much."""

    month: str
    papers_held: int
    catalog_papers: int | None


class CategoryCensusResponse(BaseModel):
    # The same categories, in the same order, in every month: the panel exists
    # to compare months, and a per-month top list would silently change axes
    # between the bars a reader is comparing.
    categories: list[str]
    # arXiv's name for each listed code that has one (category_names.py);
    # a code outside cs is absent and shows as itself.
    category_names: dict[str, str]
    months: list[CensusMonth]
    excluded: list[ExcludedMonth]


class UptakeWork(BaseModel):
    """A work from the earlier month, and how much of the later month cites it.

    `work` is the same shape the foundations table ranks, so a row here opens
    the same detail view rather than a second, thinner one. Both numbers are
    kept because they answer different questions: `work.cited_by` is how much
    the corpus cites it at all, `citations_from` is how much of that arrived
    from a single following month.
    """

    work: Foundation
    citations_from: int


class UptakeResponse(BaseModel):
    """Papers from one month already cited by the next month's papers.

    Both months must be complete, and consecutive: the measurement is "how
    fast did this land", and neither a missing citing month (too few citers)
    nor a gap between the two (more time to accumulate) measures that.
    """

    from_month: str | None
    to_month: str | None
    works: list[UptakeWork]
    works_total: int
    edges_total: int


def next_month(yymm: str) -> str:
    """The id-month after `yymm` — "2612" -> "2701"."""
    year, month = int(yymm[:2]), int(yymm[2:])
    return f"{year + 1:02d}01" if month == 12 else f"{year:02d}{month + 1:02d}"


def complete_months(coverage: list[MonthBucket], min_coverage: float) -> list[str]:
    """Id-months we hold at least `min_coverage` of the catalog's count for.

    A month with no catalog count cannot qualify: unknown coverage is not
    coverage, and MonthBucket already reports None when the snapshot predates
    the month.
    """
    return [
        bucket.month
        for bucket in coverage
        if bucket.catalog_papers and bucket.papers_held / bucket.catalog_papers >= min_coverage
    ]


def _category_census(
    conn: sqlite3.Connection, coverage: list[MonthBucket], months: list[str], top: int
) -> tuple[list[str], list[CensusMonth]]:
    if not months:
        return [], []
    placeholders = ",".join("?" * len(months))
    rows = conn.execute(
        "SELECT substr(arxiv_id, 1, 4) AS month, primary_category AS category,"
        "       count(*) AS papers"
        f"  FROM papers WHERE substr(arxiv_id, 1, 4) IN ({placeholders})"
        " GROUP BY month, category",
        months,
    ).fetchall()
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["category"]] = totals.get(row["category"], 0) + row["papers"]
    # Ranked over the whole census, then ordered by name inside the response?
    # No: by size, because the bars are drawn in this order and a reader reads
    # the first one as the largest.
    ranked = sorted(totals, key=lambda cat: (-totals[cat], cat))[:top]
    by_month = {bucket.month: bucket for bucket in coverage}
    out: list[CensusMonth] = []
    for month in months:
        held = {row["category"]: row["papers"] for row in rows if row["month"] == month}
        listed = [CategoryShare(category=cat, papers=held.get(cat, 0)) for cat in ranked]
        bucket = by_month[month]
        out.append(
            CensusMonth(
                month=month,
                papers=bucket.papers_held,
                # complete_months already refused a month without a census.
                catalog_papers=bucket.catalog_papers or 0,
                categories=listed,
                other=bucket.papers_held - sum(share.papers for share in listed),
            )
        )
    return ranked, out


def _uptake(
    conn: sqlite3.Connection, from_month: str, to_month: str, limit: int, max_authors: int
) -> tuple[list[UptakeWork], int, int]:
    rows = conn.execute(
        "SELECT w.arxiv_id, w.title, w.authors, w.primary_category, w.year, w.version,"
        "       count(*) AS cited_by,"
        "       sum(substr(cit.citing_id, 1, 4) = ?) AS citations_from"
        "  FROM citations cit"
        "  JOIN cited_works w ON w.arxiv_id = cit.cited_id"
        " WHERE substr(cit.cited_id, 1, 4) = ?"
        " GROUP BY cit.cited_id"
        " HAVING citations_from > 0"
        # arxiv_id breaks ties, so the order survives a rebuild unchanged.
        " ORDER BY citations_from DESC, w.arxiv_id"
        " LIMIT ?",
        (to_month, from_month, limit),
    ).fetchall()
    works_total, edges_total = conn.execute(
        "SELECT count(DISTINCT cit.cited_id), count(*)"
        "  FROM citations cit"
        " WHERE substr(cit.cited_id, 1, 4) = ? AND substr(cit.citing_id, 1, 4) = ?",
        (from_month, to_month),
    ).fetchone()
    works = [
        UptakeWork(
            work=Foundation(
                arxiv_id=row["arxiv_id"],
                title=row["title"],
                authors=trim_authors(row["authors"], max_authors),
                primary_category=row["primary_category"],
                year=row["year"],
                version=row["version"],
                cited_by=row["cited_by"],
            ),
            citations_from=row["citations_from"],
        )
        for row in rows
    ]
    return works, works_total, edges_total


@router.get("/api/census/categories", response_model=CategoryCensusResponse)
def get_category_census(
    top: int = Query(default=8, ge=1, le=20),
    settings: Settings = Depends(get_settings),
) -> CategoryCensusResponse:
    """What arXiv cs posted, by primary category, in the months we hold whole."""
    # Keyed on the file's identity: build_indexes writes a new corpus.db and
    # renames it over the old one, so a rebuild changes the inode and the next
    # request recomputes. Uncached this was ~1.5 s, three catalog passes.
    stat = settings.corpus_db_path.stat()
    return _cached_category_census(
        str(settings.corpus_db_path),
        stat.st_ino,
        stat.st_mtime_ns,
        top,
        settings.landing_census_min_coverage,
        settings.landing_cohort_min_share,
    )


@lru_cache(maxsize=8)
def _cached_category_census(
    db_path: str,
    _inode: int,
    _mtime_ns: int,
    top: int,
    min_coverage: float,
    min_share: float,
) -> CategoryCensusResponse:
    conn = db.connect_corpus(Path(db_path))
    try:
        coverage = month_coverage(conn)
        months = complete_months(coverage, min_coverage)
        categories, census = _category_census(conn, coverage, months, top)
        cohort = set(cohort_months(conn, min_share))
        complete = set(months)
        excluded = [
            ExcludedMonth(
                month=bucket.month,
                papers_held=bucket.papers_held,
                catalog_papers=bucket.catalog_papers,
            )
            for bucket in coverage
            if bucket.month in cohort and bucket.month not in complete
        ]
        names = {code: name for code in categories if (name := category_name(code))}
        return CategoryCensusResponse(
            categories=categories, category_names=names, months=census, excluded=excluded
        )
    finally:
        conn.close()


@router.get("/api/census/uptake", response_model=UptakeResponse)
def get_uptake(settings: Settings = Depends(get_settings)) -> UptakeResponse:
    """Work from one complete month that the next complete month already cites."""
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        months = complete_months(month_coverage(conn), settings.landing_census_min_coverage)
        pairs = [(a, b) for a, b in zip(months, months[1:], strict=False) if next_month(a) == b]
        if not pairs:
            return UptakeResponse(
                from_month=None, to_month=None, works=[], works_total=0, edges_total=0
            )
        from_month, to_month = pairs[-1]
        works, works_total, edges_total = _uptake(
            conn,
            from_month,
            to_month,
            settings.landing_uptake_limit,
            settings.landing_max_authors,
        )
        return UptakeResponse(
            from_month=from_month,
            to_month=to_month,
            works=works,
            works_total=works_total,
            edges_total=edges_total,
        )
    finally:
        conn.close()
