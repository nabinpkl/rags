"""Tests for askrag.retrieval.hybrid_search — RRF math, pushdown, degradation."""

import pytest

from askrag.config import Settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.retrieval.hybrid_search import Filters, HybridSearch, ScoredChunk, rrf_fuse


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


# --- RRF math: checkable by hand (D8) ----------------------------------------


def test_rrf_math_by_hand():
    fused = rrf_fuse({"vector": ["a", "b"], "bm25": ["b", "c"]}, rrf_k=60)
    assert fused["a"] == (pytest.approx(1 / 61), "vector")
    assert fused["b"] == (pytest.approx(1 / 62 + 1 / 61), "both")
    assert fused["c"] == (pytest.approx(1 / 62), "bm25")
    # b appears in both legs -> outranks either single-leg chunk.
    ranked = sorted(fused, key=lambda c: fused[c][0], reverse=True)
    assert ranked == ["b", "a", "c"]


def test_rrf_empty_legs_fuse_to_nothing():
    assert rrf_fuse({"vector": [], "bm25": []}, rrf_k=60) == {}


# --- search over a real (tmp) corpus.db with faked vector side ---------------


def paper(arxiv_id, cats, year, version="v2"):
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories=cats,
        published=f"{year}-01-01",
        version=version,
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


CHUNKS = [
    ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 2, "attention is all you need", 5),
    ChunkRow("2401.00001#1", "2401.00001", "Method", 3, 3, "chain of thought prompting", 5),
    ChunkRow("2401.00002#0", "2401.00002", "Intro", 1, 1, "graph attention networks", 4),
    ChunkRow("1901.00003#0", "1901.00003", "Intro", 1, 1, "attention for translation", 4),
]


@pytest.fixture
def corpus_db(tmp_path):
    papers = [
        paper("2401.00001", "cs.CL cs.AI", 2024),
        paper("2401.00002", "cs.DS", 2024),
        paper("1901.00003", "cs.CL", 2019, version=None),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, papers, CHUNKS)
    return path


class FakeEmbedder:
    def __init__(self, fail=False):
        self.fail = fail
        self.queries: list[str] = []

    def embed_query(self, text):
        if self.fail:
            raise RuntimeError("model exploded")
        self.queries.append(text)
        return [1.0, 0.0]


class FakeStore:
    def __init__(self, ids):
        self.ids = ids
        self.calls: list[dict] = []

    def query(self, embedding, k, *, category=None, year_min=None, year_max=None):
        self.calls.append(
            {"k": k, "category": category, "year_min": year_min, "year_max": year_max}
        )
        return self.ids[:k]


def searcher(corpus_db, embedder=None, store=None, **settings_overrides) -> HybridSearch:
    return HybridSearch(
        Settings(**settings_overrides),
        embedder=embedder if embedder is not None else FakeEmbedder(),
        vector_store=store if store is not None else FakeStore(["2401.00001#1"]),
        corpus_db_path=corpus_db,
    )


def test_search_fuses_legs_and_hydrates_provenance(corpus_db):
    s = searcher(corpus_db, store=FakeStore(["2401.00001#1", "2401.00001#0"]))
    results = s.search("attention prompting", k=4)
    assert all(isinstance(r, ScoredChunk) for r in results)
    by_id = {r.chunk_id: r for r in results}
    # 2401.00001#1 is in both legs (vector rank 1; bm25 matches 'prompting').
    assert by_id["2401.00001#1"].leg == "both"
    assert results[0].chunk_id == "2401.00001#1"  # both-legs chunk outranks
    hit = by_id["2401.00001#0"]
    assert (hit.paper_id, hit.section, hit.page_start, hit.page_end) == (
        "2401.00001",
        "Intro",
        1,
        2,
    )
    assert hit.version == "v2"
    assert "attention" in hit.text


def test_filters_push_down_to_both_legs(corpus_db):
    store = FakeStore(["2401.00001#0"])
    s = searcher(corpus_db, store=store)
    results = s.search("attention", filters=Filters(category="cs.CL", year_min=2024), k=4)
    # Vector leg received the filters verbatim...
    assert store.calls == [{"k": 4, "category": "cs.CL", "year_min": 2024, "year_max": None}]
    # ...and the BM25 leg applied them in SQL: cs.DS and 2019 papers excluded.
    assert {r.paper_id for r in results} == {"2401.00001"}


def test_vector_leg_down_degrades_to_bm25_only(corpus_db):
    # D8's deliberate fail-soft: NO exception, BM25-only results, all legs
    # annotated bm25. (corpus.db failing stays fatal — that's the floor.)
    s = searcher(corpus_db, embedder=FakeEmbedder(fail=True))
    results = s.search("attention", k=4)
    assert results  # BM25 still found chunks
    assert all(r.leg == "bm25" for r in results)


def test_missing_version_surfaces_as_none_not_v_something(corpus_db):
    s = searcher(corpus_db, store=FakeStore([]))
    results = s.search("translation", k=4)
    assert results[0].paper_id == "1901.00003"
    assert results[0].version is None  # D9 fallback is the caller's decision


def test_k_caps_fused_results(corpus_db):
    s = searcher(corpus_db, store=FakeStore(["2401.00001#0", "2401.00001#1"]))
    assert len(s.search("attention networks translation", k=2)) == 2


def test_rerank_flag_is_honest_about_not_existing(corpus_db):
    s = searcher(corpus_db, rerank_enabled=True)
    with pytest.raises(NotImplementedError, match="evals"):
        s.search("anything")


def test_blank_query_returns_nothing_not_garbage(corpus_db):
    # Observed live (#16): an empty query reached the vector leg, embedded
    # the bare task prefix, and returned whatever chunks sat near it.
    embedder = FakeEmbedder()
    s = searcher(corpus_db, embedder=embedder)
    assert s.search("") == []
    assert s.search("   ") == []
    assert embedder.queries == []  # the vector leg was never consulted
