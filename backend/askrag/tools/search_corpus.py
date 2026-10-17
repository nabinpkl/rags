"""tool: search_corpus — hybrid retrieval, wrapped at the tool boundary (§5).

`SearchCorpusArgs` is a closed schema (`extra="forbid"`): the model can only
ever supply the three arXiv filter fields that `sources.arxiv.filters` maps
onto the source-agnostic `retrieval.filters.Filters`, never an open filter
dict; that closed shape is this tool's "schema enum" enforcement (§5). `k`
is clamped so one call can't ask for more than `search_corpus_max_k` chunks.

Reranked when `rerank_enabled` (D8); the dollars that costs ride back on
the result for the turn's budget, outside the model payload.

Read-only by construction: `HybridSearch.search` only ever opens
`db.connect_corpus` (mode=ro, §4c) and queries the embedded Chroma store.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from askrag.config import Settings, get_settings
from askrag.retrieval.hybrid_search import HybridSearch, ScoredChunk
from askrag.sources import arxiv

# The JSON schema's advertised ceiling for `k` (review finding, PR #57: `ge=1`
# alone left the model-facing schema silent about the real limit). Read off
# Settings' own default rather than a second literal — config.py stays the
# one place `search_corpus_max_k` is declared; run() still clamps against the
# ACTUAL settings passed in, so an overridden config ceiling is still honored
# even where this static schema bound can't see it.
_DEFAULT_MAX_K = Settings.model_fields["search_corpus_max_k"].default


class SearchCorpusArgs(BaseModel):
    """Model-facing args: a closed set of fields, never an open filter dict."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="natural-language or keyword search query")
    category: str | None = Field(default=None, description="arXiv primary category, e.g. cs.CL")
    year_min: int | None = Field(default=None, description="inclusive lower bound on paper year")
    year_max: int | None = Field(default=None, description="inclusive upper bound on paper year")
    k: int = Field(default=10, ge=1, le=_DEFAULT_MAX_K, description="number of chunks to return")


@dataclass(frozen=True)
class SearchCorpusResult:
    chunks: tuple[ScoredChunk, ...]
    # What the search billed (query embedding plus rerank). The loop adds it
    # to the turn's spend (D11); it never reaches the model.
    usd: float

    def to_model_payload(self) -> dict[str, Any]:
        return {"chunks": [arxiv.chunk_payload(c) for c in self.chunks]}


def run(
    args: SearchCorpusArgs,
    *,
    scope: tuple[str, ...] | None = None,
    searcher: HybridSearch | None = None,
    settings: Settings | None = None,
) -> SearchCorpusResult:
    """`scope` is set by the ROUTE, never by the model.

    It is absent from `SearchCorpusArgs` on purpose: a model-authored paper-id
    list would be a scope the model could widen, which is not a scope. A turn
    entered from a landing-page claim carries that claim's indexed papers here,
    and no argument the model writes can reach past them.
    """
    settings = settings if settings is not None else get_settings()
    searcher = searcher if searcher is not None else HybridSearch(settings, arxiv.index(settings))
    k = min(args.k, settings.search_corpus_max_k)
    filters = arxiv.filters(
        category=args.category,
        year_min=args.year_min,
        year_max=args.year_max,
        paper_ids=scope,
    )
    outcome = searcher.search_priced(args.query, filters=filters, k=k)
    return SearchCorpusResult(chunks=tuple(outcome.chunks), usd=outcome.usd)
