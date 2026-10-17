"""Tests for askrag.retrieval.build_index: a whole non-arXiv index pair."""

import sqlite3

import pytest

from askrag.config import Settings
from askrag.retrieval.build_index import IndexBuildError, IndexChunk, IndexDocument, build_index
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import HybridSearch
from askrag.retrieval.index_location import IndexLocation

DOCS = [
    IndexDocument("s1", "deploy", 20261001, None, (("project", "rags"),)),
    IndexDocument("s2", "map", 20261015, None, (("project", "tmp"),)),
]
CHUNKS = [
    IndexChunk("s1#0", "s1", "deploy", 1, 1, "caddy serves the paper map", 5),
    IndexChunk("s2#0", "s2", "map", 1, 2, "deck.gl labels on zoom", 4),
]
VECTORS = {"s1#0": [1.0, 0.0], "s2#0": [0.0, 1.0]}


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def location(tmp_path):
    return IndexLocation(tmp_path / "idx" / "index.db", tmp_path / "idx" / "chroma", "toy_2")


def build(location, chunks=CHUNKS, ids=None):
    ids = ids if ids is not None else [c.chunk_id for c in chunks]
    return build_index(location, DOCS, chunks, ids, [VECTORS[i] for i in ids], add_batch_size=1)


class AxisEmbedder:
    def embed_query_priced(self, text):
        return ([0.0, 1.0] if "labels" in text else [1.0, 0.0]), None


def test_the_built_pair_is_searchable_by_both_legs_with_filters(location):
    assert build(location) == 2
    search = HybridSearch(Settings(rerank_enabled=False), location, embedder=AxisEmbedder())
    hits = search.search("labels", k=2)
    assert hits[0].chunk_id == "s2#0" and hits[0].leg == "both"
    tmp_only = search.search("caddy labels", filters=Filters(facets=(("project", "tmp"),)), k=2)
    assert [h.doc_id for h in tmp_only] == ["s2"]
    early = search.search("caddy labels", filters=Filters(day_max=20261010), k=2)
    assert [h.chunk_id for h in early] == ["s1#0"]


def test_a_chunk_without_a_vector_fails_before_anything_is_written(location):
    with pytest.raises(IndexBuildError, match="1 chunk\\(s\\) without a vector"):
        build(location, ids=["s1#0"])
    assert not location.db_path.exists()


def test_orphan_chunks_and_bad_ids_are_refused(location):
    with pytest.raises(IndexBuildError, match="no document"):
        build(location, chunks=[IndexChunk("s9#0", "s9", "x", 1, 1, "t", 1)], ids=[])
    with pytest.raises(IndexBuildError, match="not <doc_id>#<seq>"):
        build(location, chunks=[IndexChunk("s2#0", "s1", "x", 1, 1, "t", 1)], ids=[])


def test_a_rebuild_replaces_the_previous_pair(location):
    build(location)
    build(location, chunks=CHUNKS[:1])
    conn = sqlite3.connect(location.db_path)
    assert conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0] == 1
    conn.close()
