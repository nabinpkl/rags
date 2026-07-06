"""tool: read_paper — extracted text spans by paper id + page range (§5/§6c).

Reads from `chunks` (already extracted, section-chunked text — D6/D7), never
from `corpus/pdfs/` — this tool has no PDF bytes to serve or cache even by
accident (§6b: PDFs reach users only via their own browser hitting arxiv.org,
D9). Every span is truncated to `quote_max_words` words and the whole result
is capped to `max_quotes_per_paper` spans (§6c) — the tool physically cannot
hand back a paper's full text, independent of whatever the eventual
answer-level display cap (frontend, #26+) also does.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

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
    truncated: bool  # this span held more than quote_max_words words


@dataclass(frozen=True)
class ReadPaperResult:
    paper_id: str
    spans: tuple[TextSpan, ...]
    spans_available: int  # chunks matching the page range, before the max_quotes_per_paper cap


def _truncate_words(text: str, max_words: int) -> tuple[str, bool]:
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]), True


def _make_span(row: sqlite3.Row, max_words: int) -> TextSpan:
    text, truncated = _truncate_words(row["text"], max_words)
    return TextSpan(
        section=row["section"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        text=text,
        truncated=truncated,
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

        query = "SELECT section, page_start, page_end, text FROM chunks WHERE paper_id = ?"
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

    capped = rows[: settings.max_quotes_per_paper]
    spans = tuple(_make_span(row, settings.quote_max_words) for row in capped)
    return ReadPaperResult(paper_id=args.paper_id, spans=spans, spans_available=len(rows))
