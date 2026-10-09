"""GET /api/papers/{id} — one indexed paper's record for the reader, read-only
(spec §4c).

§6c: `chunks.text` reaches the wire from exactly one place, this route's
`?chunks=` lookup, capped server-side to `quote_max_words` words *
`max_quotes_per_paper` quotes (§6c row 4, D-1). Every other field is
metadata (§6b row 5).

This module used to also serve `GET /api/papers` (browse and search) and
`GET /api/facets` for the `/app` explorer. Both went with that page
(2026-09-30): the lists are the catalog's now (`routes_catalog.py`), and the
RAG demo filters the catalog to the indexed set.

The `facets` field below is the corpus's five DIVERSITY facets (spec §1:
authority, niche_idf, author_novelty, revisions, venue_rigor), a different
sense of "facet" than the catalog's category/month counts (D-2, issue #27).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from askrag import db
from askrag.config import Settings, get_settings

router = APIRouter()

# Column name == facet name for all five (build_indexes.py's papers schema),
# so no map is needed.
_DIVERSITY_FACET_NAMES = (
    "authority",
    "niche_idf",
    "author_novelty",
    "revisions",
    "venue_rigor",
)


# --- response models (Pydantic — the typegen source of truth) --------------


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
        if n_chunks == 0:
            # Not indexed (D16, issue #73): the reader serves the indexed
            # corpus only, so an existing-but-unindexed id is indistinguishable
            # from unknown — no half-loaded viewer for a paper the agent
            # beside it cannot read.
            raise HTTPException(status_code=404, detail=f"no paper with id {paper_id!r}")

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
