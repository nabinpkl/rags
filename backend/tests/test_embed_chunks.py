"""Tests for askrag.ingest.embed_chunks — faked backend, no network, no key."""

import json

import httpx
import pyarrow.parquet as pq
import pytest

from askrag.config import Settings
from askrag.ingest import embed_chunks
from askrag.ingest.embed_chunks import (
    BatchEmbedding,
    ChunkText,
    EmbeddingError,
    TransientEmbeddingError,
    VoyageEmbeddings,
)

DIMS = 8  # small dims keep fixtures readable; the real 512 is config


def vector_for(text: str) -> list[float]:
    # Deterministic per-text vector so round-trips are checkable.
    return [float(len(text) + i) for i in range(DIMS)]


class FakeBackend:
    """Records every call; optionally fails the first N calls."""

    def __init__(self, fail_first: int = 0, exc: Exception | None = None):
        self.calls: list[list[str]] = []
        self._failures_left = fail_first
        self._exc = exc or TransientEmbeddingError("HTTP 429 from embeddings API")

    def embed(self, texts: list[str]) -> BatchEmbedding:
        if self._failures_left > 0:
            self._failures_left -= 1
            raise self._exc
        self.calls.append(list(texts))
        return BatchEmbedding(
            vectors=[vector_for(t) for t in texts],
            total_tokens=sum(len(t) for t in texts),
        )


def write_chunks(path, chunks: list[ChunkText]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in chunks:
            record = {
                "chunk_id": c.chunk_id,
                "paper_id": c.chunk_id.split("#")[0],
                "section": "s",
                "page_start": 1,
                "page_end": 1,
                "text": c.text,
                "n_tokens": c.n_tokens,
            }
            fh.write(json.dumps(record) + "\n")


def make_chunks(n: int, tokens_each: int = 10) -> list[ChunkText]:
    return [ChunkText(f"p{i:03d}#0", f"text of chunk {i:03d}", tokens_each) for i in range(n)]


@pytest.fixture
def paths(tmp_path):
    return {
        "chunks": tmp_path / "chunks.jsonl",
        "vectors": tmp_path / "vectors.parquet",
        "shards": tmp_path / "vectors_shards",
    }


def run(paths, backend, **kwargs):
    kwargs.setdefault("dims", DIMS)
    kwargs.setdefault("batch_max_items", 4)
    kwargs.setdefault("batch_max_tokens", 10_000)
    kwargs.setdefault("usd_per_mtok", 0.02)
    kwargs.setdefault("retry_max_attempts", 3)
    kwargs.setdefault("retry_base_seconds", 0.0)
    return embed_chunks.run(
        chunks_path=paths["chunks"],
        vectors_path=paths["vectors"],
        shards_dir=paths["shards"],
        backend=backend,
        **kwargs,
    )


def read_vectors(paths) -> dict[str, list[float]]:
    table = pq.read_table(paths["vectors"])
    return dict(zip(table["chunk_id"].to_pylist(), table["vector"].to_pylist(), strict=True))


# --- batching ----------------------------------------------------------------


def test_batches_respect_item_and_token_caps():
    chunks = make_chunks(7, tokens_each=10)
    by_items = embed_chunks._batches(chunks, max_items=3, max_tokens=10_000)
    assert [len(b) for b in by_items] == [3, 3, 1]
    by_tokens = embed_chunks._batches(chunks, max_items=100, max_tokens=25)
    assert [len(b) for b in by_tokens] == [2, 2, 2, 1]
    # An oversized single chunk still ships alone rather than stalling.
    huge = [ChunkText("h#0", "x", 999)]
    assert [len(b) for b in embed_chunks._batches(huge, 4, 25)] == [1]


# --- round-trip + schema (issue acceptance) -----------------------------------


def test_parquet_round_trip_float32_fixed_dims(paths):
    chunks = make_chunks(6)
    write_chunks(paths["chunks"], chunks)
    backend = FakeBackend()
    stats = run(paths, backend)
    assert (stats.embedded, stats.merged) == (6, True)
    table = pq.read_table(paths["vectors"])
    assert table.schema.field("vector").type.value_type == "float"  # float32
    assert table.schema.field("vector").type.list_size == DIMS
    vectors = read_vectors(paths)
    assert set(vectors) == {c.chunk_id for c in chunks}
    assert vectors["p003#0"] == pytest.approx(vector_for("text of chunk 003"))
    assert not paths["shards"].exists()  # shards folded in and removed


def test_wrong_dims_from_api_fails_loudly(paths):
    write_chunks(paths["chunks"], make_chunks(2))

    class WrongDims(FakeBackend):
        def embed(self, texts):
            return BatchEmbedding(vectors=[[0.0] * (DIMS - 1) for _ in texts], total_tokens=1)

    with pytest.raises(EmbeddingError, match="dims"):
        run(paths, WrongDims())


# --- resume: no duplicates, no drops ------------------------------------------


def test_resume_after_crash_mid_run(paths):
    chunks = make_chunks(10)
    write_chunks(paths["chunks"], chunks)

    class CrashAfterTwo(FakeBackend):
        def embed(self, texts):
            if len(self.calls) == 2:
                raise RuntimeError("simulated crash mid-run")
            return super().embed(texts)

    with pytest.raises(RuntimeError):
        run(paths, CrashAfterTwo())
    # Two shards survived (atomic writes); no merged file yet.
    assert len(list(paths["shards"].glob("*.parquet"))) == 2
    assert not paths["vectors"].exists()

    backend = FakeBackend()
    stats = run(paths, backend)
    assert stats.already_embedded == 8
    assert stats.embedded == 2 and stats.merged
    # Every chunk exactly once; the resumed run only sent the missing texts.
    assert sorted(read_vectors(paths)) == sorted(c.chunk_id for c in chunks)
    assert {t for call in backend.calls for t in call} == {c.text for c in chunks[8:]}


def test_stray_tmp_shard_is_ignored(paths):
    write_chunks(paths["chunks"], make_chunks(3))
    paths["shards"].mkdir(parents=True)
    (paths["shards"] / "shard_000000.parquet.tmp").write_bytes(b"half-written garbage")
    stats = run(paths, FakeBackend())
    assert stats.embedded == 3 and stats.merged
    assert len(read_vectors(paths)) == 3


def test_completed_run_is_a_noop(paths):
    write_chunks(paths["chunks"], make_chunks(5))
    assert run(paths, FakeBackend()).merged
    backend = FakeBackend()
    stats = run(paths, backend)
    assert (stats.already_embedded, stats.embedded, stats.batches) == (5, 0, 0)
    assert backend.calls == []


def test_new_chunks_appended_without_reembedding(paths):
    write_chunks(paths["chunks"], make_chunks(4))
    run(paths, FakeBackend())
    write_chunks(paths["chunks"], make_chunks(6))  # two new chunks appear
    backend = FakeBackend()
    stats = run(paths, backend)
    assert (stats.already_embedded, stats.embedded) == (4, 2)
    assert len(read_vectors(paths)) == 6


def test_limit_defers_merge(paths):
    write_chunks(paths["chunks"], make_chunks(6))
    stats = run(paths, FakeBackend(), limit=4)
    assert (stats.embedded, stats.merged) == (4, False)
    assert not paths["vectors"].exists()
    stats = run(paths, FakeBackend())
    assert (stats.already_embedded, stats.embedded, stats.merged) == (4, 2, True)
    assert len(read_vectors(paths)) == 6


# --- rate limits ----------------------------------------------------------------


def test_rate_limit_retries_then_succeeds(paths, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(embed_chunks.time, "sleep", sleeps.append)
    write_chunks(paths["chunks"], make_chunks(2))
    stats = run(paths, FakeBackend(fail_first=2), retry_base_seconds=2.0)
    assert stats.embedded == 2
    assert sleeps == [2.0, 4.0]  # exponential backoff honored


def test_rate_limit_exhaustion_raises(paths, monkeypatch):
    monkeypatch.setattr(embed_chunks.time, "sleep", lambda _s: None)
    write_chunks(paths["chunks"], make_chunks(1))
    with pytest.raises(EmbeddingError, match="after 3 attempts"):
        run(paths, FakeBackend(fail_first=99))


def test_server_retry_after_overrides_shorter_backoff(paths, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(embed_chunks.time, "sleep", sleeps.append)
    write_chunks(paths["chunks"], make_chunks(1))
    throttle = TransientEmbeddingError("HTTP 429 from embeddings API", retry_after=9.0)
    stats = run(paths, FakeBackend(fail_first=1, exc=throttle), retry_base_seconds=2.0)
    assert stats.embedded == 1
    assert sleeps == [9.0]  # server's ask wins over the 2.0s backoff


def test_transport_errors_retry(paths, monkeypatch):
    monkeypatch.setattr(embed_chunks.time, "sleep", lambda _s: None)
    write_chunks(paths["chunks"], make_chunks(1))
    stats = run(paths, FakeBackend(fail_first=1, exc=httpx.ConnectError("boom")))
    assert stats.embedded == 1


# --- Voyage adapter: request/response contract, offline (MockTransport) --------


def adapter(monkeypatch, handler) -> VoyageEmbeddings:
    # Env vars outrank any local .env file, so the fake key always wins.
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test-key")
    settings = Settings(embedding_dims=DIMS)
    return VoyageEmbeddings(settings, transport=httpx.MockTransport(handler))


def test_adapter_sends_voyage_contract_and_parses_response(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "embedding": [float(i)] * DIMS, "index": i}
                    for i in range(len(body["input"]))
                ],
                "model": body["model"],
                "usage": {"total_tokens": 42},
            },
        )

    with adapter(monkeypatch, handler) as backend:
        result = backend.embed(["alpha", "beta"])
    request = seen[0]
    assert request.url == "https://api.voyageai.com/v1/embeddings"
    assert request.headers["authorization"] == "Bearer pa-test-key"
    body = json.loads(request.content)
    assert body == {
        "model": "voyage-4-lite",
        "input": ["alpha", "beta"],
        "input_type": "document",
        "output_dimension": DIMS,
    }
    assert result.total_tokens == 42
    assert result.vectors == [[0.0] * DIMS, [1.0] * DIMS]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_adapter_throttle_and_5xx_are_transient(monkeypatch, status):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"Retry-After": "7"})

    with adapter(monkeypatch, handler) as backend:
        with pytest.raises(TransientEmbeddingError) as excinfo:
            backend.embed(["alpha"])
    assert excinfo.value.retry_after == 7.0


def test_adapter_client_errors_fail_loudly_not_retried(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad request"})

    with adapter(monkeypatch, handler) as backend:
        with pytest.raises(httpx.HTTPStatusError):
            backend.embed(["alpha"])


def test_adapter_missing_key_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # keep a developer's real .env out of scope
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    with pytest.raises(EmbeddingError, match="VOYAGE_API_KEY"):
        VoyageEmbeddings(Settings())


# --- estimate mode ---------------------------------------------------------------


def test_estimate_prices_pending_without_a_backend(paths):
    write_chunks(paths["chunks"], make_chunks(8, tokens_each=1000))
    stats = run(paths, None, estimate=True, usd_per_mtok=0.02)
    assert stats.estimated_tokens == 8000
    assert stats.estimated_usd == pytest.approx(8000 / 1e6 * 0.02)
    # After a partial run, the estimate covers only what remains.
    run(paths, FakeBackend(), limit=5)
    stats = run(paths, None, estimate=True)
    assert stats.already_embedded == 5 and stats.estimated_tokens == 3000


def test_run_without_backend_outside_estimate_raises(paths):
    write_chunks(paths["chunks"], make_chunks(1))
    with pytest.raises(EmbeddingError, match="backend"):
        run(paths, None)
