"""Tests for askrag.retrieval.index_location."""

from pathlib import Path

from askrag.retrieval.index_location import IndexLocation


def test_a_location_is_a_value():
    a = IndexLocation(Path("x.db"), Path("chroma"), "slug_512")
    assert a == IndexLocation(Path("x.db"), Path("chroma"), "slug_512")
    assert a.collection == "slug_512"
