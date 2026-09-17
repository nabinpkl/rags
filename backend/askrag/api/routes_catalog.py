"""GET /api/catalog/* — filter the WHOLE papers table, with no model in the path.

Every other list surface here is indexed-only (D16): `/api/papers`,
`/api/facets` and every agent tool hide a paper with no `chunks` rows, because
those surfaces promise retrieval and a chunk-less paper cannot be retrieved.
This one promises something different and smaller — what arXiv posted and
whether we hold it — which is true of every row in `papers`.

The scope widens and the affordance narrows together. Each row carries
`indexed`, and the client sends an indexed row to the reader and every other
row to arxiv.org, version-pinned (§6b). No dead ends, and no row implying a
capability the corpus does not have. See DECISIONS.md 2026-09-16 and the D16
amendment in the spec.

Nothing on this path loads the embedding model or an LLM. The filter is SQL
over `papers` plus BM25 over `papers_fts` (title + abstract), and the Kaggle
snapshot carries a title and abstract for every paper whether or not its PDF
was ever fetched — which is exactly why this surface can cover the whole
table when retrieval cannot.

§6c: titles, authors and the catalog abstract only. No chunk text is read on
this path, so the quote caps have nothing to cap.
"""

import re
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from askrag import db
from askrag.api.routes_landing import trim_authors
from askrag.category_names import category_name
from askrag.config import Settings, get_settings
from askrag.facets import INDEXED_PREDICATE

router = APIRouter()

Holding = Literal["all", "text", "indexed"]
Sort = Literal["relevance", "newest", "oldest", "cited"]

# What each `holding` value adds to the WHERE clause. The three values are the
# three honest answers to "what do we have of this paper": the catalog row,
# the extracted text, or a chunked and searchable copy.
HOLDING_CLAUSE: dict[Holding, str | None] = {
    "all": None,
    "text": "papers.has_text = 1",
    "indexed": INDEXED_PREDICATE,
}

# Ordering, and the tiebreak that makes a page boundary stable across
# requests: without it two papers sharing a date can swap between pages and
# the reader sees one of them twice.
SORT_CLAUSE: dict[Sort, str] = {
    "relevance": "bm25(papers_fts), papers.arxiv_id",
    "newest": "papers.published DESC, papers.arxiv_id DESC",
    "oldest": "papers.published ASC, papers.arxiv_id ASC",
    "cited": "cited_by DESC, papers.arxiv_id",
}

_MONTH = re.compile(r"^[0-9]{4}$")
# A word the FTS tokenizer will accept. Everything else in the raw box is
# punctuation, which fts5 reads as syntax.
_TOKEN = re.compile(r'"[^"]+"|[A-Za-z0-9][A-Za-z0-9.+-]*')


class CatalogPaper(BaseModel):
    """One paper as the catalog knows it, plus what we hold of it.

    `indexed` is what decides where a row can send the reader, so it is a
    field rather than something the client infers from a count.
    """

    arxiv_id: str
    title: str
    authors: str | None
    abstract: str
    primary_category: str
    published: str
    version: str | None  # NULL => unpinned arxiv.org URL (D9/§6b)
    has_text: bool
    indexed: bool
    cited_by: int  # citations from the papers we parsed; 0 for most of the table
    # No thumbnail field: the card image lives at /thumbs/{arxiv_id}.jpg,
    # rendered on first request (D19), so there is nothing here for the
    # corpus to know or for this response to carry.
    #
    # The paper's own licence URL, on the wire because the card has to SHOW it:
    # a CC licence permits the crop above on condition that the licence is
    # named beside the attribution (D19). NULL where the seed had none.
    license: str | None


class CatalogPapersResponse(BaseModel):
    papers: list[CatalogPaper]
    total: int
    # None on the last page. Offsets are stable because corpus.db is a
    # read-only snapshot for the life of a deploy (D12) — nothing can insert
    # a row under a reader mid-scroll.
    next_offset: int | None


class CatalogBucket(BaseModel):
    value: str
    papers: int
    # The category's arXiv name, on category buckets whose code has one.
    name: str | None = None


class CatalogFacetsResponse(BaseModel):
    """Counts for the three dimensions the filter offers as lists.

    Each dimension is counted with every OTHER filter applied but not its own,
    so the numbers answer "what would I get if I picked this instead", which
    is the question a reader is asking when they look at the list.
    """

    holdings: list[CatalogBucket]  # keyed by Holding, in HOLDING_CLAUSE order
    categories: list[CatalogBucket]
    months: list[CatalogBucket]
    total: int


def fts_query(raw: str) -> str | None:
    """A raw search box turned into an fts5 MATCH expression, or None.

    fts5 reads its input as a query language, so an unbalanced quote or a
    trailing `AND` from someone who is still typing raises OperationalError
    mid-keystroke. Pulling out the words and quoting each one keeps every
    partial input valid; a quoted phrase survives as a phrase.
    """
    tokens = _TOKEN.findall(raw)
    if not tokens:
        return None
    return " AND ".join(token if token.startswith('"') else f'"{token}"' for token in tokens)


def _filters(
    q: str | None, category: str | None, month: str | None, holding: Holding
) -> tuple[list[str], list[object]]:
    """The WHERE fragments shared by the page query, the total and the facets."""
    clauses: list[str] = []
    params: list[object] = []
    if q:
        clauses.append("papers_fts MATCH ?")
        params.append(q)
    if category:
        clauses.append("papers.primary_category = ?")
        params.append(category)
    if month:
        clauses.append("substr(papers.arxiv_id, 1, 4) = ?")
        params.append(month)
    holding_clause = HOLDING_CLAUSE[holding]
    if holding_clause:
        clauses.append(holding_clause)
    return clauses, params


def _from(q: str | None) -> str:
    """The FROM clause. The FTS table joins in only when there is a query to
    match: an unconstrained `papers_fts` join would multiply every row."""
    return (
        " FROM papers JOIN papers_fts ON papers_fts.rowid = papers.rowid" if q else " FROM papers"
    )


def _where(clauses: list[str]) -> str:
    return f" WHERE {' AND '.join(clauses)}" if clauses else ""


def _page(
    conn: sqlite3.Connection,
    *,
    q: str | None,
    category: str | None,
    month: str | None,
    holding: Holding,
    sort: Sort,
    limit: int,
    offset: int,
    max_authors: int,
) -> tuple[list[CatalogPaper], int]:
    clauses, params = _filters(q, category, month, holding)
    where = _where(clauses)
    total = conn.execute(f"SELECT count(*){_from(q)}{where}", params).fetchone()[0]
    rows = conn.execute(
        "SELECT papers.arxiv_id, papers.title, papers.authors, papers.abstract,"
        "       papers.primary_category, papers.published, papers.version, papers.has_text,"
        "       papers.license,"
        f"      {INDEXED_PREDICATE} AS indexed,"
        "       (SELECT count(*) FROM citations WHERE cited_id = papers.arxiv_id) AS cited_by"
        f"{_from(q)}{where}"
        f" ORDER BY {SORT_CLAUSE[sort]} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    papers = [
        CatalogPaper(
            arxiv_id=row["arxiv_id"],
            title=row["title"],
            authors=trim_authors(row["authors"], max_authors),
            abstract=row["abstract"],
            primary_category=row["primary_category"],
            published=row["published"],
            version=row["version"],
            has_text=bool(row["has_text"]),
            indexed=bool(row["indexed"]),
            cited_by=row["cited_by"],
            license=row["license"],
        )
        for row in rows
    ]
    return papers, total


def _count(
    conn: sqlite3.Connection,
    q: str | None,
    category: str | None,
    month: str | None,
    holding: Holding,
) -> int:
    clauses, params = _filters(q, category, month, holding)
    return conn.execute(f"SELECT count(*){_from(q)}{_where(clauses)}", params).fetchone()[0]


def _facet(
    conn: sqlite3.Connection,
    expression: str,
    clauses: list[str],
    params: list[object],
    q: str | None,
) -> list[CatalogBucket]:
    rows = conn.execute(
        f"SELECT {expression} AS value, count(*) AS papers"
        f"{_from(q)}{_where(clauses)}"
        " GROUP BY value ORDER BY papers DESC, value",
        params,
    ).fetchall()
    return [CatalogBucket(value=row["value"], papers=row["papers"]) for row in rows]


@router.get("/api/catalog/papers", response_model=CatalogPapersResponse)
def list_catalog_papers(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=32),
    month: str | None = Query(default=None, description="id-month, e.g. 2608"),
    holding: Holding = "all",
    sort: Sort = "newest",
    limit: int = Query(default=0, ge=0, le=200),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> CatalogPapersResponse:
    """Every paper the catalog knows, filtered. Indexed and not, together."""
    if month is not None and not _MONTH.match(month):
        raise HTTPException(status_code=422, detail="month must be a 4-digit id-month, e.g. 2608")
    match = fts_query(q) if q else None
    if sort == "relevance" and match is None:
        raise HTTPException(status_code=422, detail="sort=relevance needs a q to rank against")
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        papers, total = _page(
            conn,
            q=match,
            category=category,
            month=month,
            holding=holding,
            sort=sort,
            limit=limit or settings.catalog_page_size,
            offset=offset,
            max_authors=settings.landing_max_authors,
        )
    finally:
        conn.close()
    next_offset = offset + len(papers)
    return CatalogPapersResponse(
        papers=papers, total=total, next_offset=next_offset if next_offset < total else None
    )


@router.get("/api/catalog/facets", response_model=CatalogFacetsResponse)
def get_catalog_facets(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=32),
    month: str | None = Query(default=None),
    holding: Holding = "all",
    settings: Settings = Depends(get_settings),
) -> CatalogFacetsResponse:
    """How many papers each category and each month would give under this filter."""
    if month is not None and not _MONTH.match(month):
        raise HTTPException(status_code=422, detail="month must be a 4-digit id-month, e.g. 2608")
    match = fts_query(q) if q else None
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        # Each dimension drops its own filter, so picking a second category
        # shows what that category holds rather than an empty intersection.
        by_category, params_c = _filters(match, None, month, holding)
        by_month, params_m = _filters(match, category, None, holding)
        return CatalogFacetsResponse(
            holdings=[
                CatalogBucket(value=value, papers=_count(conn, match, category, month, value))
                for value in HOLDING_CLAUSE
            ],
            categories=[
                bucket.model_copy(update={"name": category_name(bucket.value)})
                for bucket in _facet(conn, "papers.primary_category", by_category, params_c, match)
            ],
            months=_facet(conn, "substr(papers.arxiv_id, 1, 4)", by_month, params_m, match),
            total=_count(conn, match, category, month, holding),
        )
    finally:
        conn.close()
