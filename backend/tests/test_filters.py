"""Tests for askrag.retrieval.filters."""

import pytest

from askrag.retrieval.filters import Filters


def test_no_scope_is_not_an_empty_scope():
    assert not Filters().empty_scope
    assert not Filters(doc_ids=("a",)).empty_scope
    assert Filters(doc_ids=()).empty_scope


@pytest.mark.parametrize("key", ["Category", "facet key", "", "a;b", "x" * 40])
def test_facet_keys_are_lowercase_identifiers(key):
    with pytest.raises(ValueError, match="identifier"):
        Filters(facets=((key, "v"),))


def test_facet_values_are_free_text():
    assert Filters(facets=(("project", "rags rag-core; v2"),)).facets[0][1] == "rags rag-core; v2"
