"""Tests for askrag.retrieval.embeddings — the query role of the one factory."""

import pytest

from askrag.config import Settings
from askrag.ingest.embed_chunks import BatchEmbedding
from askrag.retrieval import embeddings
from askrag.retrieval.embeddings import QueryEmbedder


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


class FakeBackend:
    def __init__(self):
        self.seen: list[list[str]] = []

    def embed(self, texts):
        self.seen.append(texts)
        return BatchEmbedding(vectors=[[0.1, 0.2] for _ in texts], total_tokens=0)


def test_embed_query_returns_single_vector():
    backend = FakeBackend()
    embedder = QueryEmbedder(Settings(), backend=backend)
    assert embedder.embed_query("what is attention") == [0.1, 0.2]
    assert backend.seen == [["what is attention"]]


def test_production_wiring_uses_query_input_kind(monkeypatch):
    # THE contract this module exists for (#16 warning): the real backend is
    # constructed in query mode, so search_query: prefixing can never be
    # skipped — recall degrades silently if this regresses.
    captured: dict = {}

    def fake_make_backend(settings, *, input_kind="document"):
        captured["input_kind"] = input_kind
        return FakeBackend()

    monkeypatch.setattr(embeddings, "make_backend", fake_make_backend)
    QueryEmbedder(Settings())
    assert captured["input_kind"] == "query"
