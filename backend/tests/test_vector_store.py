"""Tests for askrag.retrieval.vector_store — the pgvector seam (D4)."""

import chromadb
import chromadb.config
import pytest

from askrag.config import Settings
from askrag.retrieval.vector_store import VectorStore, VectorStoreError

DIMS = 4
SLUG = f"fake-embed_{DIMS}"  # Settings(embedding_model="fake/fake-embed").slug


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def settings() -> Settings:
    return Settings(embedding_model="fake/fake-embed", embedding_dims=DIMS)


AXES = {"a#0": 0, "b#0": 1, "c#0": 2}
META = {
    "a#0": {"paper_id": "a", "category": "cs.CL", "year": 2024},
    "b#0": {"paper_id": "b", "category": "cs.DS", "year": 2024},
    "c#0": {"paper_id": "c", "category": "cs.CL", "year": 2019},
}


def axis_vector(i: int) -> list[float]:
    v = [0.0] * DIMS
    v[i] = 1.0
    return v


@pytest.fixture
def chroma_dir(tmp_path):
    path = tmp_path / "chroma"
    client = chromadb.PersistentClient(
        path=str(path), settings=chromadb.config.Settings(anonymized_telemetry=False)
    )
    collection = client.create_collection(SLUG, configuration={"hnsw": {"space": "cosine"}})
    collection.add(
        ids=list(AXES),
        embeddings=[axis_vector(i) for i in AXES.values()],
        metadatas=[META[cid] for cid in AXES],
    )
    return path


def test_query_returns_rank_ordered_chunk_ids(chroma_dir):
    store = VectorStore(settings(), chroma_dir=chroma_dir)
    assert store.query(axis_vector(1), k=1) == ["b#0"]
    assert store.query(axis_vector(1), k=3)[0] == "b#0"


def test_filters_push_into_where(chroma_dir):
    store = VectorStore(settings(), chroma_dir=chroma_dir)
    # b#0 is the nearest but cs.DS — the filter must exclude it at the store.
    assert store.query(axis_vector(1), k=3, category="cs.CL") == ["a#0", "c#0"]
    assert store.query(axis_vector(1), k=3, category="cs.CL", year_min=2024) == ["a#0"]
    assert store.query(axis_vector(1), k=3, year_max=2019) == ["c#0"]


def test_missing_collection_is_a_named_error(tmp_path):
    empty = tmp_path / "empty-chroma"
    chromadb.PersistentClient(  # a store exists, the collection does not
        path=str(empty), settings=chromadb.config.Settings(anonymized_telemetry=False)
    )
    with pytest.raises(VectorStoreError, match=SLUG):
        VectorStore(settings(), chroma_dir=empty)
