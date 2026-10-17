"""Tests for askrag.sources.arxiv: the arXiv mapping onto the contract."""

from askrag.config import Settings
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import ScoredChunk
from askrag.sources import arxiv


def test_year_bounds_become_whole_year_day_bounds():
    f = arxiv.filters(category="cs.CL", year_min=2024, year_max=2025, paper_ids=("2401.00001",))
    assert f == Filters(
        doc_ids=("2401.00001",),
        day_min=20240101,
        day_max=20251231,
        facets=(("category", "cs.CL"),),
    )


def test_no_arguments_filter_nothing():
    assert arxiv.filters() == Filters()


def test_the_tool_payload_keeps_the_arxiv_contract_names():
    """The agent's prompts and §5's tool contract name paper_id and pages."""
    chunk = ScoredChunk("2401.00001#3", "2401.00001", "Method", 4, 5, "text", 0.03, "both", "v2")
    payload = arxiv.chunk_payload(chunk)
    assert payload == {
        "chunk_id": "2401.00001#3",
        "paper_id": "2401.00001",
        "section": "Method",
        "page_start": 4,
        "page_end": 5,
        "text": "text",
        "score": 0.03,
        "leg": "both",
        "version": "v2",
    }


def test_the_index_is_corpus_db_and_the_model_slug_collection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(corpus_dir=tmp_path)
    location = arxiv.index(settings)
    assert location.db_path == tmp_path / "corpus.db"
    assert location.chroma_dir == tmp_path / "chroma"
    assert location.collection == settings.embedding_model_slug
