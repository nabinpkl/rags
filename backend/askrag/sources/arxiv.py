"""arXiv as a retrieval source (D21): its index contract, filters and payload.

corpus.db keeps its own schema (`papers`, `chunks` and the catalog tables the
pages read), so the contract relations are views over it rather than a second
copy that could drift: a document is a paper, a position is a PDF page, the
day is the paper's published date, and the one facet is its primary
category. build_indexes creates these views; the FTS table is the contract's
own `rag_chunks_fts` over `chunks`.

The model-facing payload keeps the arXiv names (`paper_id`, `page_start`)
that the agent's prompts and tool contract (§5) were written against.
"""

from dataclasses import asdict
from typing import Any

from askrag.config import Settings
from askrag.retrieval import index_schema
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import ScoredChunk
from askrag.retrieval.index_location import IndexLocation

CATEGORY = "category"

# A paper without a published date falls back to Jan 1 of its year, which is
# exactly what `papers.year` already falls back to, so a year filter reads the
# same either way.
VIEWS_DDL = f"""
CREATE VIEW {index_schema.DOCUMENTS} AS
    SELECT arxiv_id AS doc_id, title,
           CASE WHEN length(published) >= 10
                THEN CAST(replace(substr(published, 1, 10), '-', '') AS INTEGER)
                ELSE year * 10000 + 101 END AS day,
           version
    FROM papers;
CREATE VIEW {index_schema.CHUNKS} AS
    SELECT rowid AS chunk_rowid, chunk_id, paper_id AS doc_id, section,
           page_start AS pos_start, page_end AS pos_end, text, n_tokens
    FROM chunks;
CREATE VIEW {index_schema.FACETS} AS
    SELECT arxiv_id AS doc_id, '{CATEGORY}' AS key, primary_category AS value
    FROM papers;
"""

FTS_DDL = index_schema.fts_ddl("chunks", "rowid")


def index(settings: Settings) -> IndexLocation:
    return IndexLocation(
        db_path=settings.corpus_db_path,
        chroma_dir=settings.chroma_dir,
        collection=settings.embedding_model_slug,
    )


def year_day(year: int, *, end: bool = False) -> int:
    return year * 10000 + (1231 if end else 101)


def filters(
    *,
    category: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    paper_ids: tuple[str, ...] | None = None,
) -> Filters:
    return Filters(
        doc_ids=paper_ids,
        day_min=year_day(year_min) if year_min is not None else None,
        day_max=year_day(year_max, end=True) if year_max is not None else None,
        facets=((CATEGORY, category),) if category is not None else (),
    )


def chunk_payload(chunk: ScoredChunk) -> dict[str, Any]:
    """One hit in the arXiv tool contract's names."""
    fields = asdict(chunk)
    return {
        "chunk_id": fields["chunk_id"],
        "paper_id": fields["doc_id"],
        "section": fields["section"],
        "page_start": fields["pos_start"],
        "page_end": fields["pos_end"],
        "text": fields["text"],
        "score": fields["score"],
        "leg": fields["leg"],
        "version": fields["version"],
    }
