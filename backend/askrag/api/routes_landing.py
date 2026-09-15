"""GET /api/landing, GET /api/foundations/{id} — the citation graph the front door ranks.

The landing page answers "what is computer science building on right now?" from
counted citations, with every number opening the papers behind it.

**Why these routes do not apply `INDEXED_PREDICATE`, and why D16 still holds.**
Everything here counts over `citations`, and a count of citations is not an offer
of retrieval: 1,174 papers really do cite Qwen3, whether or not we hold any of
their text. What D16 forbids is the app surfacing a paper it cannot retrieve —
so every LIST these routes return is restricted to indexed papers, while the
COUNTS are the honest totals. The page then reads "8 of 1,174", and every one of
the 8 opens. No `readable` flag reaches the wire, no two-tier UI, no badges;
D16's rule is unchanged, only the reason it is affordable (the indexed set is
now derived from this page's manifest — see `ingest/select_frontier.py`).

Alias discipline: `citations` is aliased `cit` throughout, because
`facets.INDEXED_PREDICATE` uses `c` for its own `chunks` subquery and a silent
alias collision would scope the wrong table.

**Our numbers are ours, and a claim about arXiv carries its denominator.**
Every count here is over papers WE hold. That is honest as long as it is not
spoken as a claim about the literature, and for one release it was: the page
said "every cs paper arXiv posted in the window", which measured 94% for July
2026, 49% for August and 5% for September. So `catalog_months` (the Kaggle
census, `ingest/kaggle_seed.count_cs_papers_by_id_month`) travels with the
cohort and with every month bucket, and a month whose denominator is unknown
says so instead of borrowing a wrong one.

§6c: nothing here returns `chunks.text`. The landing surface is metadata and
counts only; paper text reaches the wire solely through routes_explorer's capped
cited-excerpt path.
"""

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from askrag import db
from askrag.config import Settings, get_settings
from askrag.facets import INDEXED_PREDICATE

router = APIRouter()


class CohortStats(BaseModel):
    """What the page opens with: the cohort it counted, and how complete it is.

    There is no "window" here any more, and that is the point. The window was
    `min/max(citing id-month)`, which 261 old seed papers (1.5% of the citing
    side) stretched from two months to nineteen years, and every sentence
    hanging off it then claimed we hold "every cs paper arXiv posted" across
    that span. We hold 94% of July 2026, 49% of August, 5% of September and
    under 2% of everything else.

    So the cohort is stated as what it is, with its own denominator beside it:
    `cohort_catalog_papers` is what the catalog lists for those same months
    (`catalog_months`), and it is None when the snapshot is older than the
    cohort and therefore cannot answer.

    Every field here is one a reader has a use for: how much of arXiv this
    counted, what came out of it, and how much of it the agent can actually
    read. Stage counts that only describe our pipeline do not belong on the
    wire — `papers_parsed` is the sole survivor of that kind, and only
    because the parse rate the methods note states is a percentage of it.
    """

    cohort_start: str | None  # id-month, e.g. "2607"
    cohort_end: str | None
    cohort_papers: int
    cohort_catalog_papers: int | None
    # Papers whose text reached the reference parser (`papers.has_text`), the
    # parse rate's denominator. Never printed as a count: "20,733 PDFs
    # extracted" tells a reader nothing they can use, while "81% of them
    # yielded a usable reference list" tells them how much this page's counts
    # undercount.
    papers_parsed: int
    papers_with_references: int
    citations: int
    cited_works: int
    # What the agent can search and quote (D16's indexed set). The one number
    # here that answers "what can I do on this page", as against "what did
    # they process".
    readable_papers: int


class CitedYearBucket(BaseModel):
    year: int | None
    citations: int


class Foundation(BaseModel):
    """A work our recent cohort builds on. Not a `papers` row — see cited_works."""

    arxiv_id: str
    title: str | None
    authors: str | None
    primary_category: str | None
    year: int | None
    version: str | None
    cited_by: int


class LandingResponse(BaseModel):
    stats: CohortStats
    foundations: list[Foundation]
    cited_years: list[CitedYearBucket]


class CoCitedWork(BaseModel):
    arxiv_id: str
    title: str | None
    version: str | None
    cite_both: int


class IndexedCiter(BaseModel):
    """A citing paper we hold and have indexed — every one of these opens."""

    arxiv_id: str
    title: str
    primary_category: str
    version: str | None


class FoundationDetailResponse(BaseModel):
    foundation: Foundation
    co_cited: list[CoCitedWork]
    indexed_citers: list[IndexedCiter]
    # The denominator behind `indexed_citers`, stated so the UI can say
    # "8 of 1,174" instead of implying the list is the whole set.
    total_citers: int
    # How many papers the agent actually reads for this claim — i.e. the size
    # of the scope the chat route resolves. It is NOT len(indexed_citers): the
    # list is capped for layout, while the scope is every indexed paper citing
    # this work (many arrive via other foundations' citer sets). Without this
    # the page had to say "answers come from the 8 papers we indexed", which
    # was false for every foundation — the real figure is 14-46.
    scope_size: int


class LatestPaper(BaseModel):
    """A paper we hold and have indexed, newest first. Indexed-only (D16):
    the dashboard links every row to the reader, so nothing listed may
    dead-end. Fresh-but-unindexed papers appear here on their own once the
    index run covers them — no second code path."""

    arxiv_id: str
    title: str
    authors: str | None
    primary_category: str | None
    published: str
    version: str | None
    ref_count: int


class LatestResponse(BaseModel):
    papers: list[LatestPaper]


class MonthBucket(BaseModel):
    """One id-month of the corpus, against what arXiv posted that month.

    `catalog_papers` is the whole reason this shape exists. Bar heights of
    what we hold, with no denominator, said "19 papers in October 2025" on a
    page about what CS is building on, and a reader takes that as a fact about
    October rather than about our download schedule. It is None when the
    catalog snapshot cannot answer for that month (it lists fewer papers than
    we hold, i.e. the snapshot predates the month) — unknown is printable,
    a wrong denominator is not.

    Keyed by ID-MONTH, not by `published`: the census counts id-months, and
    the two disagree by 383 papers for July 2026 alone (arXiv announces a
    late-June submission with a 2607 id), which would put the numerator and
    denominator of the same bar on different axes.
    """

    month: str  # id-month, e.g. "2607"
    papers_held: int
    papers_parsed: int
    refs_made: int
    catalog_papers: int | None


class CoverageResponse(BaseModel):
    months: list[MonthBucket]


def trim_authors(authors: str | None, max_names: int) -> str | None:
    """Cap a catalog author list to what the page shows, plus the overflow count.

    Measured 2026-08-28: untrimmed, authors were 125 KB of a 133 KB
    `/api/landing` response, and the UI rendered three names. The catalog
    separates names with commas or " and " depending on the record.
    """
    if not authors:
        return authors
    names = [n.strip() for n in re.split(r",| and ", authors) if n.strip()]
    if len(names) <= max_names:
        return ", ".join(names)
    return f"{', '.join(names[:max_names])} +{len(names) - max_names}"


def _cohort_months(conn: sqlite3.Connection, min_share: float) -> list[str]:
    """The id-months the cohort actually came from, by a stated rule.

    Rule: an id-month is in the cohort when it contributed at least
    `min_share` of the papers we parsed references from. Measured
    2026-09-15 over 16,893 parsed papers: 2607 gave 61%, 2608 36%, 2609 1.3%,
    and the next month down gave 0.24% — so any threshold between 0.3% and
    1.3% selects the same three months. The boundary is not delicate, which
    is the only reason a threshold is acceptable here.

    The alternative (min/max of the citing id-month) is what this replaces:
    261 stray seed papers put `0711` at one end and made the page claim
    nineteen years of complete coverage.
    """
    rows = conn.execute(
        "SELECT substr(citing_id, 1, 4) AS month, count(DISTINCT citing_id) AS papers"
        "  FROM citations GROUP BY month"
    ).fetchall()
    total = sum(row["papers"] for row in rows)
    if not total:
        return []
    return sorted(row["month"] for row in rows if row["papers"] / total >= min_share)


def _cohort_stats(conn: sqlite3.Connection, min_share: float) -> CohortStats:
    months = _cohort_months(conn, min_share)
    start, end = (months[0], months[-1]) if months else (None, None)
    cohort_papers = 0
    catalog_papers: int | None = None
    if months:
        placeholders = ",".join("?" * len(months))
        (cohort_papers,) = conn.execute(
            f"SELECT count(*) FROM papers WHERE substr(arxiv_id, 1, 4) IN ({placeholders})",
            months,
        ).fetchone()
        (census,) = conn.execute(
            f"SELECT sum(cs_papers) FROM catalog_months WHERE month IN ({placeholders})",
            months,
        ).fetchone()
        # A census smaller than our own holdings means the snapshot predates
        # part of the cohort; report unknown rather than a share over 100%.
        catalog_papers = census if census and census >= cohort_papers else None
    (parsed,) = conn.execute("SELECT count(*) FROM papers WHERE has_text").fetchone()
    (with_refs,) = conn.execute("SELECT count(DISTINCT citing_id) FROM citations").fetchone()
    (edges,) = conn.execute("SELECT count(*) FROM citations").fetchone()
    (works,) = conn.execute("SELECT count(DISTINCT cited_id) FROM citations").fetchone()
    (readable,) = conn.execute(f"SELECT count(*) FROM papers WHERE {INDEXED_PREDICATE}").fetchone()
    return CohortStats(
        cohort_start=start,
        cohort_end=end,
        cohort_papers=cohort_papers,
        cohort_catalog_papers=catalog_papers,
        papers_parsed=parsed,
        papers_with_references=with_refs,
        citations=edges,
        cited_works=works,
        readable_papers=readable,
    )


def _foundations(conn: sqlite3.Connection, limit: int, max_authors: int) -> list[Foundation]:
    rows = conn.execute(
        "SELECT w.arxiv_id, w.title, w.authors, w.primary_category, w.year, w.version,"
        "       count(*) AS cited_by"
        "  FROM citations cit"
        "  JOIN cited_works w ON w.arxiv_id = cit.cited_id"
        " GROUP BY cit.cited_id"
        # arxiv_id breaks ties so the ranking is stable across rebuilds — a
        # page whose order shuffles on rerun cannot be read as a trend.
        " ORDER BY cited_by DESC, w.arxiv_id"
        " LIMIT ?",
        (limit,),
    ).fetchall()
    return [_to_foundation(row, max_authors) for row in rows]


def _to_foundation(row: sqlite3.Row, max_authors: int) -> Foundation:
    fields = dict(row)
    fields["authors"] = trim_authors(fields["authors"], max_authors)
    return Foundation(**fields)


def find_foundation(
    conn: sqlite3.Connection, arxiv_id: str, max_authors: int = 6
) -> Foundation | None:
    """One cited work with its citation count, or None. Public: routes_chat
    uses it to 404 an unknown scope rather than run the turn unscoped."""
    row = conn.execute(
        "SELECT w.arxiv_id, w.title, w.authors, w.primary_category, w.year, w.version,"
        "       count(*) AS cited_by"
        "  FROM citations cit"
        "  JOIN cited_works w ON w.arxiv_id = cit.cited_id"
        " WHERE cit.cited_id = ?"
        " GROUP BY cit.cited_id",
        (arxiv_id,),
    ).fetchone()
    return _to_foundation(row, max_authors) if row else None


def _cited_years(conn: sqlite3.Connection) -> list[CitedYearBucket]:
    """How far back this cohort reaches — the card that makes the corpus legible."""
    rows = conn.execute(
        "SELECT w.year AS year, count(*) AS citations"
        "  FROM citations cit"
        "  JOIN cited_works w ON w.arxiv_id = cit.cited_id"
        " GROUP BY w.year"
        " ORDER BY w.year"
    ).fetchall()
    return [CitedYearBucket(**dict(row)) for row in rows]


def _co_cited(conn: sqlite3.Connection, arxiv_id: str, limit: int) -> list[CoCitedWork]:
    """Works cited alongside this one, by how many papers cite both.

    A plain count with NO bibliography-size cap: "N papers cite both" is then
    literally what the number means, with nothing filtered out behind it. The
    prototype capped bibliographies at 60 refs to stop surveys dominating; that
    cap turns out to be unnecessary here — measured 2026-08-28 over the real
    graph, the median paper carries 6 arXiv refs, the largest carries 490, and
    that largest one contributes ZERO to the headline Qwen3 x Llama-3 pair
    (290). Re-measure before adding a cap back.
    """
    rows = conn.execute(
        "SELECT other.cited_id AS arxiv_id, w.title, w.version, count(*) AS cite_both"
        "  FROM citations cit"
        "  JOIN citations other"
        "    ON other.citing_id = cit.citing_id AND other.cited_id <> cit.cited_id"
        "  JOIN cited_works w ON w.arxiv_id = other.cited_id"
        " WHERE cit.cited_id = ?"
        " GROUP BY other.cited_id"
        " ORDER BY cite_both DESC, other.cited_id"
        " LIMIT ?",
        (arxiv_id, limit),
    ).fetchall()
    return [CoCitedWork(**dict(row)) for row in rows]


def _indexed_citers(conn: sqlite3.Connection, arxiv_id: str, limit: int) -> list[IndexedCiter]:
    """Citing papers the agent can actually read — newest first (D16).

    The count on the page is every citer; this list is only the indexed ones,
    so nothing the reader can click fails to open.
    """
    rows = conn.execute(
        "SELECT papers.arxiv_id, papers.title, papers.primary_category, papers.version"
        "  FROM citations cit"
        "  JOIN papers ON papers.arxiv_id = cit.citing_id"
        f" WHERE cit.cited_id = ? AND {INDEXED_PREDICATE}"
        " ORDER BY papers.arxiv_id DESC"
        " LIMIT ?",
        (arxiv_id, limit),
    ).fetchall()
    return [IndexedCiter(**dict(row)) for row in rows]


def scope_paper_ids(conn: sqlite3.Connection, arxiv_id: str) -> tuple[str, ...]:
    """The indexed papers a question about `arxiv_id` may be answered from.

    Resolved SERVER-SIDE and never model-authored (§5/§6): the agent receives a
    scope it cannot widen, in the same posture as `drive_ui`'s enums. Includes
    the foundation itself when we hold it, since "what does this paper say?" is
    the most obvious question to ask from its own card.

    Deliberately UNBOUNDED: capping it would silently narrow a scope, which is
    worse than a big one. The scope becomes an SQL `IN` list downstream
    (`fts.search_bm25`) and a Chroma `$in`, so the real ceiling is SQLite's
    parameter limit — 32,766 on the bundled build, against a frontier that
    yields single digits per foundation today.
    """
    rows = conn.execute(
        "SELECT papers.arxiv_id FROM citations cit"
        "  JOIN papers ON papers.arxiv_id = cit.citing_id"
        f" WHERE cit.cited_id = ? AND {INDEXED_PREDICATE}"
        " UNION"
        " SELECT papers.arxiv_id FROM papers"
        f" WHERE papers.arxiv_id = ? AND {INDEXED_PREDICATE}",
        (arxiv_id, arxiv_id),
    ).fetchall()
    return tuple(row[0] for row in rows)


@router.get("/api/landing", response_model=LandingResponse)
def get_landing(
    limit: int | None = Query(default=None, ge=1, le=200),
    settings: Settings = Depends(get_settings),
) -> LandingResponse:
    """The whole front page in one call — it is one static composition.

    `limit` defaults to `frontier_top_cited` because that setting IS the
    manifest select_frontier.py indexed against: a smaller default would
    silently hide foundations whose papers we fetched, chunked and embedded,
    and a larger one would list foundations with no indexed citers behind them.
    """
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        return LandingResponse(
            stats=_cohort_stats(conn, settings.landing_cohort_min_share),
            foundations=_foundations(
                conn,
                limit if limit is not None else settings.frontier_top_cited,
                settings.landing_max_authors,
            ),
            cited_years=_cited_years(conn),
        )
    finally:
        conn.close()


@router.get("/api/foundations/{arxiv_id}", response_model=FoundationDetailResponse)
def get_foundation(
    arxiv_id: str,
    co_cited_limit: int = Query(default=8, ge=1, le=50),
    citers_limit: int | None = Query(default=None, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> FoundationDetailResponse:
    # citers_limit defaults to frontier_citers_per_work for the same reason
    # `limit` above does: that setting is how many citers were indexed per work.
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        foundation = find_foundation(conn, arxiv_id, settings.landing_max_authors)
        if foundation is None:
            raise HTTPException(status_code=404, detail=f"no cited work with id {arxiv_id!r}")
        return FoundationDetailResponse(
            foundation=foundation,
            co_cited=_co_cited(conn, arxiv_id, co_cited_limit),
            indexed_citers=_indexed_citers(
                conn,
                arxiv_id,
                citers_limit if citers_limit is not None else settings.frontier_citers_per_work,
            ),
            scope_size=len(scope_paper_ids(conn, arxiv_id)),
            total_citers=foundation.cited_by,
        )
    finally:
        conn.close()


def _latest(conn: sqlite3.Connection, limit: int, max_authors: int) -> list[LatestPaper]:
    # Newest INDEXED papers only (D16 — every row links to the reader).
    # The inner query picks the N newest, the outer counts their references;
    # counting before the limit would scan the whole citations table.
    rows = conn.execute(
        "SELECT p.arxiv_id, p.title, p.authors, p.primary_category, p.published,"
        "       p.version, count(cit.cited_id) AS ref_count"
        "  FROM (SELECT * FROM papers"
        f"         WHERE {INDEXED_PREDICATE}"
        "         ORDER BY published DESC, arxiv_id DESC"
        "         LIMIT ?) p"
        "  LEFT JOIN citations cit ON cit.citing_id = p.arxiv_id"
        " GROUP BY p.arxiv_id"
        " ORDER BY p.published DESC, p.arxiv_id DESC",
        (limit,),
    ).fetchall()
    papers = []
    for row in rows:
        fields = dict(row)
        fields["authors"] = trim_authors(fields["authors"], max_authors)
        papers.append(LatestPaper(**fields))
    return papers


def _coverage(conn: sqlite3.Connection) -> list[MonthBucket]:
    """What we hold per id-month, beside what the catalog lists for it.

    Counts are honest totals (CohortStats posture), so no indexed
    restriction: this describes the corpus we collected, not the part the
    agent can answer from.

    LEFT JOIN on the census, not an inner one: a month we hold papers for but
    the snapshot does not cover still belongs in the series, with an unknown
    denominator (see MonthBucket).
    """
    rows = conn.execute(
        "SELECT substr(p.arxiv_id, 1, 4) AS month,"
        "       count(DISTINCT p.arxiv_id) AS papers_held,"
        "       count(DISTINCT CASE WHEN p.has_text THEN p.arxiv_id END) AS papers_parsed,"
        "       count(cit.cited_id) AS refs_made,"
        "       cm.cs_papers AS catalog_papers"
        "  FROM papers p"
        "  LEFT JOIN citations cit ON cit.citing_id = p.arxiv_id"
        "  LEFT JOIN catalog_months cm ON cm.month = substr(p.arxiv_id, 1, 4)"
        " GROUP BY month"
        " ORDER BY month"
    ).fetchall()
    return [
        MonthBucket(
            month=row["month"],
            papers_held=row["papers_held"],
            papers_parsed=row["papers_parsed"],
            refs_made=row["refs_made"],
            # Same guard as the cohort's: a census below our own holdings is
            # a stale snapshot, not a coverage above 100%.
            catalog_papers=(
                row["catalog_papers"]
                if row["catalog_papers"] and row["catalog_papers"] >= row["papers_held"]
                else None
            ),
        )
        for row in rows
    ]


@router.get("/api/latest", response_model=LatestResponse)
def get_latest(
    limit: int = Query(default=8, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> LatestResponse:
    """The dashboard's "what just landed" list — newest indexed papers."""
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        return LatestResponse(papers=_latest(conn, limit, settings.landing_max_authors))
    finally:
        conn.close()


@router.get("/api/coverage", response_model=CoverageResponse)
def get_coverage(settings: Settings = Depends(get_settings)) -> CoverageResponse:
    """How much of each month we hold — the provenance panel's whole input."""
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        return CoverageResponse(months=_coverage(conn))
    finally:
        conn.close()
