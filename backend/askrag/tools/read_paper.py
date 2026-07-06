"""tool: read_paper — page-bounded extracted text for the MODEL's deep read
(§5/§6c row 1).

Reads from `chunks` (already extracted, section-chunked text — D6/D7), never
from `corpus/pdfs/` — this tool has no PDF bytes to serve or cache even by
accident (§6b: PDFs reach users only via their own browser hitting arxiv.org,
D9). The result is a page-ordered prefix of the matching chunks, bounded by
`read_paper_max_tokens` (summed from each chunk's stored `n_tokens`) — a real
budget for a real deep read (§6c row 1, D1), not the ≤50-word/≤3-quote
*display* cap. That cap governs verbatim quotes surfacing in an ANSWER (§6c
row 4, decisions.md 2026-07-06) and is enforced at answer-assembly (#23/#30)
and the frontend (#26) — never here.
"""

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from askrag import db
from askrag.config import Settings, get_settings


class ReadPaperError(Exception):
    """The requested paper id does not exist in corpus.db (§5)."""


class ReadPaperArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str = Field(min_length=1, description="arXiv id, e.g. 2401.00001")
    page_start: int | None = Field(default=None, ge=1, description="first page, inclusive")
    page_end: int | None = Field(default=None, ge=1, description="last page, inclusive")


@dataclass(frozen=True)
class TextSpan:
    section: str
    page_start: int
    page_end: int
    text: str


@dataclass(frozen=True)
class ReadPaperResult:
    paper_id: str
    spans: tuple[TextSpan, ...]
    spans_available: int  # chunks matching the page range, before the token budget cut
    tokens_used: int  # sum of the returned spans' stored n_tokens
    truncated: bool  # more chunks matched than read_paper_max_tokens allowed through

    def to_model_payload(self) -> dict[str, Any]:
        # Explicit dict, not bare `asdict(self)`: asdict() would leave
        # `spans` as a tuple of dicts, not the plain list a JSON-facing
        # payload should carry (§5/§6 fence seam, 2026-07-06 checkpoint
        # finding 2).
        return {
            "paper_id": self.paper_id,
            "spans": [asdict(s) for s in self.spans],
            "spans_available": self.spans_available,
            "tokens_used": self.tokens_used,
            "truncated": self.truncated,
        }


def _make_span(row: sqlite3.Row) -> TextSpan:
    return TextSpan(
        section=row["section"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        text=row["text"],
    )


def run(
    args: ReadPaperArgs,
    *,
    settings: Settings | None = None,
    corpus_db_path: Path | None = None,
) -> ReadPaperResult:
    settings = settings if settings is not None else get_settings()
    conn = db.connect_corpus(corpus_db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM papers WHERE arxiv_id = ?", (args.paper_id,)
        ).fetchone()
        if exists is None:
            raise ReadPaperError(f"no paper with id {args.paper_id!r} in corpus.db")

        query = (
            "SELECT section, page_start, page_end, text, n_tokens FROM chunks WHERE paper_id = ?"
        )
        params: list[object] = [args.paper_id]
        if args.page_start is not None:
            query += " AND page_end >= ?"
            params.append(args.page_start)
        if args.page_end is not None:
            query += " AND page_start <= ?"
            params.append(args.page_end)
        query += " ORDER BY page_start"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    # Page-ordered prefix under the token budget. Always take at least one
    # chunk even if it alone exceeds the budget — the tool must not go silent
    # on a paper whose single matching chunk is oversized.
    included: list[sqlite3.Row] = []
    tokens_used = 0
    for row in rows:
        if included and tokens_used + row["n_tokens"] > settings.read_paper_max_tokens:
            break
        included.append(row)
        tokens_used += row["n_tokens"]

    spans = tuple(_make_span(row) for row in included)
    return ReadPaperResult(
        paper_id=args.paper_id,
        spans=spans,
        spans_available=len(rows),
        tokens_used=tokens_used,
        truncated=len(included) < len(rows),
    )
