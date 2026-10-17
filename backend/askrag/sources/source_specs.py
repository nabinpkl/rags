"""The sources retrieval can search (D21): a literal dict, no discovery (§4d).

Each source names where its index lives and the settings its searches run
under. A source whose text must stay on this machine overrides the embedding
backend to local here, so its queries embed locally too.
"""

from collections.abc import Callable
from dataclasses import dataclass

from askrag.config import Settings
from askrag.retrieval.index_location import IndexLocation
from askrag.sources import arxiv
from askrag.sources.claude_transcripts import source as claude_transcripts
from askrag.sources.claude_transcripts.chunk_sessions import PROJECT


@dataclass(frozen=True)
class SourceSpec:
    name: str
    index: Callable[[Settings], IndexLocation]
    search_settings: Callable[[Settings], Settings]
    # The facet the golden sampler stratifies by (arXiv: category).
    stratum_facet: str


def _unchanged(settings: Settings) -> Settings:
    return settings


SOURCES: dict[str, SourceSpec] = {
    "arxiv": SourceSpec(
        name="arxiv",
        index=arxiv.index,
        search_settings=_unchanged,
        stratum_facet=arxiv.CATEGORY,
    ),
    "claude_transcripts": SourceSpec(
        name="claude_transcripts",
        index=claude_transcripts.index,
        search_settings=claude_transcripts.search_settings,
        stratum_facet=PROJECT,
    ),
}
