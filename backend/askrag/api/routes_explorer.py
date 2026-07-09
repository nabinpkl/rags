"""GET /api/papers, GET /api/papers/{id}, GET /api/facets — browse/filter/
search over corpus.db, read-only (spec §4c).

Three request shapes on `/api/papers`, picked by whether `q` is set:

- `q` empty (metadata-only browse): a real SQL keyset scan over `papers`,
  ordered by `sort` with `arxiv_id` as the stable tiebreak — the path the
  issue's acceptance checklist measures ("cursor pagination correct; p95 <
  100 ms on metadata-only queries").
- `q` set (search): `HybridSearch.search()` (D8: vector+BM25, fused) returns
  a BOUNDED top-`explorer_search_k` list of chunks, collapsed to distinct
  papers (dedup by paper_id, best/first-seen fused score kept, rank
  preserved). Retrieval fundamentally returns a bounded top-k, not an
  arbitrarily-deep ranked table — pagination here slices that one bounded,
  already-fetched list by cursor position; it never re-queries with a larger
  k per page. `sort` can still re-order this bounded list (e.g. by year)
  before slicing.

§6c: every `/api/papers` row exposes title/authors/abstract/score plus CC0
metadata (category/year/venue/license/version, §6b row 5) — never
`chunks.text`. `chunks.text` reaches the wire from exactly one place:
`GET /api/papers/{id}?chunks=`, capped server-side to
`quote_max_words` words * `max_quotes_per_paper` quotes (§6c row 4, D-1).

D-2 (issue #27 decisions.md): `GET /api/facets`'s category/year/license/venue
counts and the papers list's `facets=` diversity-score columns are two
DIFFERENT senses of "facet" — spec §1 names authority/niche_idf/
author_novelty/revisions/venue_rigor as the corpus's five diversity facets;
`query_metadata`/`GET /api/facets` group by the four CATEGORICAL columns
instead. Both are real, both are named "facet" in this codebase; the
distinction is documented here and in decisions.md, not renamed away.
"""

import base64
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from askrag import db, facets
from askrag.config import Settings, get_settings
from askrag.retrieval.hybrid_search import Filters, HybridSearch

router = APIRouter()

# The five diversity facets named in spec §1 — distinct from GROUP_BY_COLUMNS'
# four categorical dimensions (see module docstring). Column name == facet
# name for all five (build_indexes.py's papers schema), so no map is needed.
_DIVERSITY_FACET_NAMES = (
    "authority",
    "niche_idf",
    "author_novelty",
    "revisions",
    "venue_rigor",
)

Sort = Literal["relevance", "year_desc", "year_asc", "title_asc"]

# sort -> (papers column, descending). "relevance" isn't here: it only
# applies to the search path and isn't a SQL ORDER BY (fused score, not a
# stored column).
_SORT_COLUMNS: dict[str, tuple[str, bool]] = {
    "year_desc": ("year", True),
    "year_asc": ("year", False),
    "title_asc": ("title", False),
}


def get_hybrid_search_factory(
    settings: Settings = Depends(get_settings),
) -> Callable[[], HybridSearch]:
    """A THUNK, not an instance: FastAPI resolves every declared `Depends()`
    unconditionally before the handler runs, but `/api/papers` only needs a
    searcher on the `q`-set branch (constructing a real `HybridSearch` loads
    the embedding model + opens the Chroma collection, D8/D5) — a metadata-
    only browse request must never pay that cost or require those artifacts
    to exist. `list_papers` calls the factory itself, only inside the search
    branch. Tests override this dependency with a factory returning a fake
    satisfying `.search()`'s signature, so no real embedding model loads
    under test (house rule)."""
    return lambda: HybridSearch(settings)


# --- response models (Pydantic — the typegen source of truth) --------------


class PaperListItem(BaseModel):
    arxiv_id: str
    title: str
    authors: str
    abstract: str
    primary_category: str
    year: int
    venue: str | None
    license: str | None
    version: str | None  # NULL => unpinned PDF URL fallback (D9/§6b)
    score: float | None  # fused retrieval score; None for a metadata-only browse row
    facets: dict[str, float | int | None] | None = None  # only when `facets=` was requested


class PapersResponse(BaseModel):
    items: list[PaperListItem]
    next_cursor: str | None
    # None on the search path: a bounded top-k has no meaningful corpus-wide
    # total (see module docstring). Populated on the browse path's first
    # page only (cursor is None) — cheap at 6,460 rows, skipped on later
    # pages since the caller already has it.
    total: int | None


class CitedExcerpt(BaseModel):
    chunk_id: str
    section: str
    page_start: int
    page_end: int
    text: str  # word-capped (§6c row 4) — see _cited_excerpts


class PaperDetailResponse(BaseModel):
    arxiv_id: str
    title: str
    authors: str
    abstract: str
    categories: str
    primary_category: str
    year: int
    published: str
    venue: str | None
    license: str | None
    version: str | None  # NULL => unpinned PDF URL fallback (D9/§6b)
    facets: dict[str, float | int | None]
    n_chunks: int
    excerpts: list[CitedExcerpt]  # empty unless `?chunks=` was passed
    excerpts_truncated: bool  # more requested chunk_ids existed than the cap allowed


class FacetBucketOut(BaseModel):
    value: str | int | None
    count: int


class FacetsResponse(BaseModel):
    total: int
    category: list[FacetBucketOut]
    year: list[FacetBucketOut]
    license: list[FacetBucketOut]
    venue: list[FacetBucketOut]


# --- cursor: opaque base64(JSON) of the keyset/position state --------------


@dataclass(frozen=True)
class _CursorState:
    q: str
    category: str | None
    year_from: int | None
    year_to: int | None
    sort: str
    last_key: str | int | float | None  # None on the search path (position cursor)
    last_id: str


def _encode_cursor(state: _CursorState) -> str:
    payload = json.dumps(asdict(state), separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(raw: str) -> _CursorState:
    try:
        payload = base64.urlsafe_b64decode(raw.encode()).decode()
        data = json.loads(payload)
        return _CursorState(**data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc


def _validate_cursor_matches_request(
    cursor: _CursorState,
    *,
    q: str,
    category: str | None,
    year_from: int | None,
    year_to: int | None,
    sort: str,
) -> None:
    if (cursor.q, cursor.category, cursor.year_from, cursor.year_to, cursor.sort) != (
        q,
        category,
        year_from,
        year_to,
        sort,
    ):
        raise HTTPException(
            status_code=400, detail="cursor does not match the current q/filters/sort"
        )


def _resolve_sort(sort: str | None, q: str) -> str:
    if sort is None:
        return "relevance" if q else "year_desc"
    if sort == "relevance" and not q:
        raise HTTPException(status_code=400, detail="sort=relevance requires q")
    return sort


def _parse_facet_names(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    unknown = [n for n in names if n not in _DIVERSITY_FACET_NAMES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown facet name(s): {unknown}")
    return names


def _to_list_item(
    row: sqlite3.Row, score: float | None, facet_names: list[str] | None
) -> PaperListItem:
    return PaperListItem(
        arxiv_id=row["arxiv_id"],
        title=row["title"],
        authors=row["authors"],
        abstract=row["abstract"],
        primary_category=row["primary_category"],
        year=row["year"],
        venue=row["venue"],
        license=row["license"],
        version=row["version"],
        score=score,
        facets=({name: row[name] for name in facet_names} if facet_names else None),
    )


# --- browse path: real SQL keyset pagination --------------------------------


def _keyset_where(
    column: str, descending: bool, last_key: object, last_id: str
) -> tuple[str, list[object]]:
    op = "<" if descending else ">"
    return (
        f"({column} {op} ? OR ({column} = ? AND arxiv_id > ?))",
        [last_key, last_key, last_id],
    )


def _browse_papers(
    conn: sqlite3.Connection,
    filters: facets.CountFilters,
    sort: str,
    cursor: _CursorState | None,
    page_size: int,
) -> tuple[list[sqlite3.Row], bool]:
    column, descending = _SORT_COLUMNS[sort]
    where, params = facets.where_clause(filters)
    if cursor is not None:
        keyset_sql, keyset_params = _keyset_where(
            column, descending, cursor.last_key, cursor.last_id
        )
        where = f"{where} AND {keyset_sql}" if where else f" WHERE {keyset_sql}"
        params = [*params, *keyset_params]
    order = "DESC" if descending else "ASC"
    rows = conn.execute(
        f"SELECT * FROM papers{where} ORDER BY {column} {order}, arxiv_id ASC LIMIT ?",
        [*params, page_size + 1],
    ).fetchall()
    has_more = len(rows) > page_size
    return list(rows[:page_size]), has_more


# --- search path: bounded top-k, collapsed chunks -> papers -----------------


def _search_papers(
    searcher: HybridSearch,
    *,
    q: str,
    category: str | None,
    year_min: int | None,
    year_max: int | None,
    k: int,
) -> list[tuple[str, float]]:
    """[(paper_id, score)], deduped by paper_id. `HybridSearch.search()`
    already returns chunks ordered by fused score descending (D8), so the
    first occurrence of a paper_id IS its best-scoring chunk — no separate
    max() tracking needed."""
    chunks = searcher.search(
        q, filters=Filters(category=category, year_min=year_min, year_max=year_max), k=k
    )
    order: list[str] = []
    best_score: dict[str, float] = {}
    for c in chunks:
        if c.paper_id not in best_score:
            best_score[c.paper_id] = c.score
            order.append(c.paper_id)
    return [(pid, best_score[pid]) for pid in order]


def _hydrate_rows(conn: sqlite3.Connection, paper_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not paper_ids:
        return {}
    placeholders = ",".join("?" * len(paper_ids))
    rows = conn.execute(
        f"SELECT * FROM papers WHERE arxiv_id IN ({placeholders})", paper_ids
    ).fetchall()
    return {r["arxiv_id"]: r for r in rows}


# --- GET /api/papers ---------------------------------------------------------


@router.get("/api/papers", response_model=PapersResponse)
def list_papers(
    q: str = Query(default=""),
    category: str | None = Query(default=None),
    year_from: int | None = Query(default=None),
    year_to: int | None = Query(default=None),
    facets_param: str | None = Query(default=None, alias="facets"),
    sort: Sort | None = Query(default=None),
    cursor: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    hybrid_search_factory: Callable[[], HybridSearch] = Depends(get_hybrid_search_factory),
) -> PapersResponse:
    resolved_sort = _resolve_sort(sort, q)
    facet_names = _parse_facet_names(facets_param)
    decoded_cursor = _decode_cursor(cursor) if cursor else None
    if decoded_cursor is not None:
        _validate_cursor_matches_request(
            decoded_cursor,
            q=q,
            category=category,
            year_from=year_from,
            year_to=year_to,
            sort=resolved_sort,
        )

    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        if not q:
            filters = facets.CountFilters(category=category, year_min=year_from, year_max=year_to)
            rows, has_more = _browse_papers(
                conn, filters, resolved_sort, decoded_cursor, settings.explorer_page_size
            )
            total = facets.count_scalar(conn, filters) if decoded_cursor is None else None
            items = [_to_list_item(r, None, facet_names) for r in rows]
            next_cursor = None
            if has_more and rows:
                column, _descending = _SORT_COLUMNS[resolved_sort]
                last = rows[-1]
                next_cursor = _encode_cursor(
                    _CursorState(
                        q=q,
                        category=category,
                        year_from=year_from,
                        year_to=year_to,
                        sort=resolved_sort,
                        last_key=last[column],
                        last_id=last["arxiv_id"],
                    )
                )
            return PapersResponse(items=items, next_cursor=next_cursor, total=total)

        ranked = _search_papers(
            hybrid_search_factory(),
            q=q,
            category=category,
            year_min=year_from,
            year_max=year_to,
            k=settings.explorer_search_k,
        )
        rows_by_id = _hydrate_rows(conn, [pid for pid, _score in ranked])
        entries = [(rows_by_id[pid], score) for pid, score in ranked if pid in rows_by_id]
        if resolved_sort != "relevance":
            column, descending = _SORT_COLUMNS[resolved_sort]
            entries.sort(key=lambda e: e[0][column], reverse=descending)

        start = 0
        if decoded_cursor is not None:
            ids = [row["arxiv_id"] for row, _score in entries]
            try:
                start = ids.index(decoded_cursor.last_id) + 1
            except ValueError:
                start = len(entries)  # cursor's anchor no longer present -> empty page
        page = entries[start : start + settings.explorer_page_size]
        has_more = start + settings.explorer_page_size < len(entries)
        items = [_to_list_item(row, score, facet_names) for row, score in page]
        next_cursor = None
        if has_more and page:
            last_row, _score = page[-1]
            next_cursor = _encode_cursor(
                _CursorState(
                    q=q,
                    category=category,
                    year_from=year_from,
                    year_to=year_to,
                    sort=resolved_sort,
                    last_key=None,
                    last_id=last_row["arxiv_id"],
                )
            )
        return PapersResponse(items=items, next_cursor=next_cursor, total=None)
    finally:
        conn.close()


# --- GET /api/papers/{id} ----------------------------------------------------


def _cap_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])


def _cited_excerpts(
    conn: sqlite3.Connection, paper_id: str, requested_ids: list[str], settings: Settings
) -> tuple[list[CitedExcerpt], bool]:
    """§6c row 4 enforced HERE and ONLY here (D-1, issue #27): at most
    `max_quotes_per_paper` chunks, each capped to `quote_max_words` words.
    This is the sole route through which `chunks.text` reaches the wire."""
    capped_ids = requested_ids[: settings.max_quotes_per_paper]
    truncated = len(requested_ids) > settings.max_quotes_per_paper
    if not capped_ids:
        return [], truncated
    placeholders = ",".join("?" * len(capped_ids))
    rows = conn.execute(
        f"SELECT chunk_id, section, page_start, page_end, text FROM chunks "
        f"WHERE paper_id = ? AND chunk_id IN ({placeholders}) ORDER BY page_start",
        [paper_id, *capped_ids],
    ).fetchall()
    excerpts = [
        CitedExcerpt(
            chunk_id=r["chunk_id"],
            section=r["section"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            text=_cap_words(r["text"], settings.quote_max_words),
        )
        for r in rows
    ]
    return excerpts, truncated


@router.get("/api/papers/{paper_id}", response_model=PaperDetailResponse)
def get_paper(
    paper_id: str,
    chunks: str | None = Query(
        default=None, description="comma-separated chunk_ids for the capped cited-excerpt lookup"
    ),
    settings: Settings = Depends(get_settings),
) -> PaperDetailResponse:
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        row = conn.execute("SELECT * FROM papers WHERE arxiv_id = ?", (paper_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no paper with id {paper_id!r}")
        (n_chunks,) = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE paper_id = ?", (paper_id,)
        ).fetchone()

        excerpts: list[CitedExcerpt] = []
        excerpts_truncated = False
        if chunks:
            requested_ids = [c.strip() for c in chunks.split(",") if c.strip()]
            excerpts, excerpts_truncated = _cited_excerpts(conn, paper_id, requested_ids, settings)

        return PaperDetailResponse(
            arxiv_id=row["arxiv_id"],
            title=row["title"],
            authors=row["authors"],
            abstract=row["abstract"],
            categories=row["categories"],
            primary_category=row["primary_category"],
            year=row["year"],
            published=row["published"],
            venue=row["venue"],
            license=row["license"],
            version=row["version"],
            facets={name: row[name] for name in _DIVERSITY_FACET_NAMES},
            n_chunks=n_chunks,
            excerpts=excerpts,
            excerpts_truncated=excerpts_truncated,
        )
    finally:
        conn.close()


# --- GET /api/facets ----------------------------------------------------------


@router.get("/api/facets", response_model=FacetsResponse)
def get_facets(
    category: str | None = Query(default=None),
    year_from: int | None = Query(default=None),
    year_to: int | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> FacetsResponse:
    filters = facets.CountFilters(category=category, year_min=year_from, year_max=year_to)
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        total = facets.count_scalar(conn, filters)
        dims: dict[str, list[FacetBucketOut]] = {}
        for dim in facets.GROUP_BY_COLUMNS:
            buckets, _truncated = facets.count_grouped(
                conn, dim, filters, settings.explorer_facets_max_groups
            )
            dims[dim] = [FacetBucketOut(value=b.value, count=b.count) for b in buckets]
        return FacetsResponse(
            total=total,
            category=dims["category"],
            year=dims["year"],
            license=dims["license"],
            venue=dims["venue"],
        )
    finally:
        conn.close()
