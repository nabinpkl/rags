"""Tests for askrag.ask: the source-aware search CLI."""

import argparse

import pytest

from askrag import ask
from askrag.retrieval.filters import Filters
from askrag.retrieval.hybrid_search import ScoredChunk


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def test_facet_flags_parse_as_key_value():
    assert ask._facet("project=rags") == ("project", "rags")
    with pytest.raises(argparse.ArgumentTypeError):
        ask._facet("project")


class FakeSearch:
    instances: list["FakeSearch"] = []

    def __init__(self, settings, index):
        self.index = index
        self.calls: list[tuple[str, Filters | None, int | None]] = []
        FakeSearch.instances.append(self)

    def search(self, query, filters=None, k=None):
        self.calls.append((query, filters, k))
        return [ScoredChunk("s#0", "s", "deploy", 1, 2, "caddy 404", 0.03, "both", None)]


def test_main_searches_the_named_source_with_the_flags(monkeypatch, capsys):
    monkeypatch.setattr(ask, "HybridSearch", FakeSearch)
    assert ask.main(["caddy", "--facet", "category=cs.CL", "--day-min", "20260101", "-k", "3"]) == 0
    search = FakeSearch.instances[-1]
    assert search.index.db_path.name == "corpus.db"
    assert search.calls == [
        ("caddy", Filters(day_min=20260101, facets=(("category", "cs.CL"),)), 3)
    ]
    assert "s - | deploy | @1-2 |" in capsys.readouterr().out
