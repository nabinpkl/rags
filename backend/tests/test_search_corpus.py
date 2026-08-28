"""Tests for askrag.tools.search_corpus — the tool-boundary wrapper over
hybrid_search (§5)."""

import pytest

from askrag.config import Settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.retrieval.hybrid_search import HybridSearch, ScoredChunk
from askrag.tools.search_corpus import SearchCorpusArgs, run


def paper(arxiv_id, cats="cs.CL", year=2024):
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories=cats,
        published=f"{year}-01-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


CHUNKS = [
    ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "attention is all you need", 5),
]


@pytest.fixture
def corpus_db(tmp_path):
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, [paper("2401.00001")], CHUNKS)
    return path


class FakeEmbedder:
    def embed_query(self, text):
        return [1.0, 0.0]


class FakeStore:
    def __init__(self, ids):
        self.ids = ids
        self.calls: list[dict] = []

    def query(self, embedding, k, *, category=None, year_min=None, year_max=None, paper_ids=None):
        self.calls.append({"k": k, "paper_ids": paper_ids})
        if paper_ids is not None:
            wanted = set(paper_ids)
            return [i for i in self.ids if i.split("#")[0] in wanted][:k]
        return self.ids[:k]


def test_run_wraps_hybrid_search_and_returns_scored_chunks(corpus_db):
    searcher = HybridSearch(
        Settings(),
        embedder=FakeEmbedder(),
        vector_store=FakeStore(["2401.00001#0"]),
        corpus_db_path=corpus_db,
    )
    result = run(SearchCorpusArgs(query="attention"), searcher=searcher)
    assert all(isinstance(c, ScoredChunk) for c in result.chunks)
    assert result.chunks[0].paper_id == "2401.00001"


def test_to_model_payload_is_a_plain_dict_of_chunk_dicts(corpus_db):
    searcher = HybridSearch(
        Settings(),
        embedder=FakeEmbedder(),
        vector_store=FakeStore(["2401.00001#0"]),
        corpus_db_path=corpus_db,
    )
    result = run(SearchCorpusArgs(query="attention"), searcher=searcher)
    payload = result.to_model_payload()
    assert isinstance(payload, dict)
    assert isinstance(payload["chunks"], list)
    assert payload["chunks"][0]["paper_id"] == "2401.00001"


def test_k_is_clamped_to_search_corpus_max_k(corpus_db):
    # 20 is within the schema's static `le` ceiling (the config default, 25)
    # but above this run's overridden settings ceiling (3) — run() must clamp
    # to the ACTUAL settings, not just the schema's advertised default.
    store = FakeStore(["2401.00001#0"])
    searcher = HybridSearch(
        Settings(search_corpus_max_k=3),
        embedder=FakeEmbedder(),
        vector_store=store,
        corpus_db_path=corpus_db,
    )
    run(
        SearchCorpusArgs(query="attention", k=20),
        searcher=searcher,
        settings=Settings(search_corpus_max_k=3),
    )
    assert store.calls == [{"k": 3, "paper_ids": None}]


def test_args_reject_an_open_filter_dict():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        SearchCorpusArgs.model_validate({"query": "x", "filters": {"anything": "goes"}})


def test_args_reject_k_past_the_schema_ceiling():
    # The JSON schema advertises a `le` bound (the config default) so the
    # model sees the real ceiling instead of an unbounded `k` (review
    # finding, PR #57).
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        SearchCorpusArgs(query="attention", k=999)


def test_args_require_a_nonblank_query():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        SearchCorpusArgs(query="")


def test_a_route_set_scope_narrows_retrieval(corpus_db):
    """The scope is a keyword the model cannot author (see search_corpus.run)."""
    store = FakeStore(["2401.00001#0"])
    searcher = HybridSearch(
        Settings(), embedder=FakeEmbedder(), vector_store=store, corpus_db_path=corpus_db
    )

    out_of_scope = run(
        SearchCorpusArgs(query="attention"),
        scope=("2499.99999",),
        searcher=searcher,
        settings=Settings(),
    )
    in_scope = run(
        SearchCorpusArgs(query="attention"),
        scope=("2401.00001",),
        searcher=searcher,
        settings=Settings(),
    )

    assert store.calls[0]["paper_ids"] == ("2499.99999",)
    assert out_of_scope.chunks == ()
    assert {c.paper_id for c in in_scope.chunks} == {"2401.00001"}


def test_scope_is_absent_from_the_model_facing_schema():
    """A scope the model can write is not a scope."""
    fields = SearchCorpusArgs.model_json_schema()["properties"]

    assert "scope" not in fields
    assert "paper_ids" not in fields
