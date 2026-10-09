"""Tests for askrag.retrieval.embeddings — the query role of the one factory."""

import httpx
import pytest

from askrag.config import Settings
from askrag.ingest.embed_chunks import BatchEmbedding, EmbeddingError
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
        return BatchEmbedding(vectors=[[0.1, 0.2] for _ in texts], total_tokens=0, usd=3e-08)


def test_embed_query_returns_single_vector():
    backend = FakeBackend()
    embedder = QueryEmbedder(Settings(), backend=backend)
    assert embedder.embed_query("what is attention") == [0.1, 0.2]
    assert backend.seen == [["what is attention"]]


def test_embed_query_priced_carries_the_billed_cost():
    embedder = QueryEmbedder(Settings(), backend=FakeBackend())
    assert embedder.embed_query_priced("what is attention") == ([0.1, 0.2], 3e-08)


class FailingBackend:
    def __init__(self, exc: Exception):
        self._exc = exc

    def embed(self, texts):
        raise self._exc


def test_transport_error_is_translated_to_embedding_error():
    # A genuine outage (connection refused, DNS, timeout) — no HTTP response
    # at all. Must land in OUR vocabulary so hybrid_search's fail-soft
    # boundary can degrade without knowing httpx exists (PR #59 review
    # finding 2).
    request = httpx.Request("POST", "https://api.voyageai.com/v1/embeddings")
    backend = FailingBackend(httpx.ConnectError("connection refused", request=request))
    embedder = QueryEmbedder(Settings(), backend=backend)
    with pytest.raises(EmbeddingError):
        embedder.embed_query("what is attention")


def test_non_retryable_4xx_propagates_unwrapped():
    # embed_chunks.py raises a bare httpx.HTTPStatusError, unwrapped, for a
    # non-retryable 4xx (our own bug/bad request) — embed_query must NOT
    # translate this into EmbeddingError, or a code bug would silently
    # degrade to BM25-only instead of failing loud (PR #59 review finding 2).
    request = httpx.Request("POST", "https://api.voyageai.com/v1/embeddings")
    response = httpx.Response(400, request=request)
    backend = FailingBackend(
        httpx.HTTPStatusError("Bad Request", request=request, response=response)
    )
    embedder = QueryEmbedder(Settings(), backend=backend)
    with pytest.raises(httpx.HTTPStatusError):
        embedder.embed_query("what is attention")


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
