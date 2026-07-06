"""tool: search_corpus — hybrid retrieval, wrapped at the tool boundary (§5).

`SearchCorpusArgs` is a closed schema (`extra="forbid"`): the model can only
ever supply the three filter fields `retrieval.hybrid_search.Filters` already
defines, never an open filter dict — that closed shape is this tool's "schema
enum" enforcement (§5). `k` is clamped so one call can't ask for more than
`search_corpus_max_k` chunks.

Read-only by construction: `HybridSearch.search` only ever opens
`db.connect_corpus` (mode=ro, §4c) and queries the embedded Chroma store.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from askrag.config import Settings, get_settings
from askrag.retrieval.hybrid_search import Filters, HybridSearch, ScoredChunk


class SearchCorpusArgs(BaseModel):
    """Model-facing args: a closed set of fields, never an open filter dict."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="natural-language or keyword search query")
    category: str | None = Field(default=None, description="arXiv primary category, e.g. cs.CL")
    year_min: int | None = Field(default=None, description="inclusive lower bound on paper year")
    year_max: int | None = Field(default=None, description="inclusive upper bound on paper year")
    k: int = Field(default=10, ge=1, description="number of chunks to return")


@dataclass(frozen=True)
class SearchCorpusResult:
    chunks: tuple[ScoredChunk, ...]


def run(
    args: SearchCorpusArgs,
    *,
    searcher: HybridSearch | None = None,
    settings: Settings | None = None,
) -> SearchCorpusResult:
    settings = settings if settings is not None else get_settings()
    searcher = searcher if searcher is not None else HybridSearch(settings)
    k = min(args.k, settings.search_corpus_max_k)
    filters = Filters(category=args.category, year_min=args.year_min, year_max=args.year_max)
    chunks = searcher.search(args.query, filters=filters, k=k)
    return SearchCorpusResult(chunks=tuple(chunks))
