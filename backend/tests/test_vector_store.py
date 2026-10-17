"""Tests for askrag.retrieval.vector_store — the pgvector seam (D4, D21)."""

import chromadb
import chromadb.config
import chromadb.errors
import pytest

from askrag.retrieval.filters import Filters
from askrag.retrieval.index_location import IndexLocation
from askrag.retrieval.vector_store import (
    VectorStore,
    VectorStoreError,
    load_collection,
    vector_metadata,
    where_clause,
)

DIMS = 4
SLUG = f"fake-embed_{DIMS}"

AXES = {"a#0": 0, "b#0": 1, "c#0": 2}
META = {
    "a#0": vector_metadata("a", 20240301, [("category", "cs.CL")]),
    "b#0": vector_metadata("b", 20240301, [("category", "cs.DS")]),
    "c#0": vector_metadata("c", 20190101, [("category", "cs.CL")]),
}


def axis_vector(i: int) -> list[float]:
    v = [0.0] * DIMS
    v[i] = 1.0
    return v


@pytest.fixture
def index(tmp_path) -> IndexLocation:
    path = tmp_path / "chroma"
    count = load_collection(
        path,
        SLUG,
        list(AXES),
        [axis_vector(i) for i in AXES.values()],
        [META[cid] for cid in AXES],
        add_batch_size=2,  # smaller than the set, so batching is exercised
    )
    assert count == 3
    return IndexLocation(tmp_path / "unused.db", path, SLUG)


def test_query_returns_rank_ordered_chunk_ids(index):
    store = VectorStore(index)
    assert store.query(axis_vector(1), k=1, filters=Filters()) == ["b#0"]
    assert store.query(axis_vector(1), k=3, filters=Filters())[0] == "b#0"


def test_filters_push_into_where(index):
    store = VectorStore(index)
    cl = (("category", "cs.CL"),)
    # b#0 is the nearest but cs.DS — the filter must exclude it at the store.
    assert store.query(axis_vector(1), k=3, filters=Filters(facets=cl)) == ["a#0", "c#0"]
    recent_cl = Filters(facets=cl, day_min=20240101)
    assert store.query(axis_vector(1), k=3, filters=recent_cl) == ["a#0"]
    assert store.query(axis_vector(1), k=3, filters=Filters(day_max=20191231)) == ["c#0"]
    assert store.query(axis_vector(1), k=3, filters=Filters(doc_ids=("c",))) == ["c#0"]


def test_an_empty_scope_returns_nothing_without_asking_chroma(index):
    assert VectorStore(index).query(axis_vector(1), k=3, filters=Filters(doc_ids=())) == []


def test_where_clause_is_none_without_filters_and_anded_with_several():
    assert where_clause(Filters()) is None
    assert where_clause(Filters(day_min=1)) == {"day": {"$gte": 1}}
    both = where_clause(Filters(day_min=1, facets=(("project", "rags"),)))
    assert both == {"$and": [{"facet_project": "rags"}, {"day": {"$gte": 1}}]}


def test_a_document_cannot_carry_two_values_for_one_facet():
    with pytest.raises(ValueError, match="two values"):
        vector_metadata("a", 1, [("category", "cs.CL"), ("category", "cs.AI")])


def test_reloading_a_collection_replaces_it(index):
    load_collection(index.chroma_dir, SLUG, ["a#0"], [axis_vector(0)], [META["a#0"]], 10)
    assert VectorStore(index).query(axis_vector(1), k=3, filters=Filters()) == ["a#0"]


def test_missing_collection_is_a_named_error(tmp_path):
    empty = tmp_path / "empty-chroma"
    chromadb.PersistentClient(  # a store exists, the collection does not
        path=str(empty), settings=chromadb.config.Settings(anonymized_telemetry=False)
    )
    with pytest.raises(VectorStoreError, match=SLUG):
        VectorStore(IndexLocation(tmp_path / "unused.db", empty, SLUG))


def test_wrong_dimension_query_is_a_code_bug_that_stays_raw(index):
    # A real chroma dimension mismatch (query embedding dims != the
    # collection's — this chromadb version raises InvalidArgumentError for
    # it, not InvalidDimensionException) is a code/config bug (drifted
    # embedding_dims), not an outage. Must propagate unchanged, never
    # wrapped as VectorStoreError (PR #59 review finding 3).
    store = VectorStore(index)
    with pytest.raises(chromadb.errors.InvalidArgumentError, match="dimension"):
        store.query([0.0, 1.0], k=1, filters=Filters())  # 2 dims, collection is DIMS=4


def test_internal_chroma_failure_is_wrapped_as_vector_store_error(index, monkeypatch):
    # A genuine store-side operational failure (corrupted index, internal
    # engine error) — must translate to OUR vocabulary so hybrid_search's
    # fail-soft boundary can degrade without knowing chromadb exists
    # (PR #59 review finding 3).
    store = VectorStore(index)

    def _broken_query(*args, **kwargs):
        raise chromadb.errors.InternalError("engine failure")

    monkeypatch.setattr(store._collection, "query", _broken_query)
    with pytest.raises(VectorStoreError, match="engine failure"):
        store.query(axis_vector(1), k=1, filters=Filters())
