"""corpus/chunks.jsonl -> corpus/vectors.parquet (D5).

Voyage AI voyage-4-lite at output_dimension=512 (D5 as amended 2026-07-05:
Voyage free tier replaces OpenAI). Raw httpx against the one REST endpoint —
no SDK (§4b: httpx is pre-approved; one POST does not justify a new dep).
Corpus chunks are embedded with input_type="document"; the query side
(retrieval/embeddings.py, #15) must use input_type="query" to match.
Parquet schema — a FROZEN interface consumed by build_indexes (#14):

    chunk_id  string                      (chunk_papers' "{paper_id}#{seq}")
    vector    fixed_size_list<float32>[embedding_dims]

Resume design: each embedded batch is written as its own shard parquet under
corpus/vectors_shards/, atomically (tmp + rename — the mechanism SIGKILL-
proven in #11), and merged into vectors.parquet only when nothing is left to
embed; shards are deleted only after the merge lands. The done-set on start
is the union of chunk_ids in vectors.parquet and every shard, deduplicated at
merge, so a killed run resumes without duplicating or dropping a chunk and a
completed run is a no-op.

The API key is read once through Settings and passed to the client
constructor; it is never logged and never appears in span attributes.
--estimate never constructs a client (no key needed): it sums the stored
n_tokens and prices them, which is also the owner's spend-approval number.

Telemetry (D15): askrag.ingest.embed run span (chunk/token/cost totals);
askrag.ingest.embed.batch child span per API call (items, tokens). Running
token + cost counters are logged per batch and use API-reported usage.
"""

import argparse
import contextlib
import email.utils
import json
import logging
import sys
import time
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from askrag import telemetry
from askrag.config import Settings, get_settings

_log = logging.getLogger("askrag.ingest.embed_chunks")

# Voyage REST endpoint (protocol fact, not a tunable).
_VOYAGE_BASE_URL = "https://api.voyageai.com/v1"


class EmbeddingError(Exception):
    """A batch could not be embedded correctly (bad dims, exhausted retries)."""


class TransientEmbeddingError(EmbeddingError):
    """429/5xx — the API contract says retry; carries Retry-After when sent.

    Any other 4xx is a bug or a bad request and fails loudly instead
    (httpx.HTTPStatusError, deliberately not retried).
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# Transport faults (connect/read/timeout) retry alongside throttling.
_RETRYABLE = (TransientEmbeddingError, httpx.TransportError)


def _parse_retry_after(header: str | None) -> float | None:
    """RFC 9110 Retry-After: delay-seconds or an HTTP-date (CDN throttle pages).

    Unparseable values degrade to None (plain exponential backoff) — a weird
    header from a middlebox must never crash a throttled run.
    """
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        pass
    try:
        target = email.utils.parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)  # RFC 9110 dates are GMT
    return max((target - datetime.now(tz=UTC)).total_seconds(), 0.0)


@dataclass(frozen=True)
class ChunkText:
    """The slice of a chunk record this stage consumes (chunk_papers #12)."""

    chunk_id: str
    text: str
    n_tokens: int


@dataclass(frozen=True)
class BatchEmbedding:
    """One embeddings-API response: vectors in input order + billed tokens."""

    vectors: list[list[float]]
    total_tokens: int


class EmbeddingsBackend(Protocol):
    def embed(self, texts: list[str]) -> BatchEmbedding: ...


class VoyageEmbeddings:
    """httpx adapter for Voyage's /embeddings; the only place the key is touched.

    Owns its httpx.Client as a context manager. `transport` is a test seam
    (httpx.MockTransport) so the request/response contract is provable offline.
    """

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        key = settings.voyage_api_key.get_secret_value()
        if not key:
            raise EmbeddingError(
                "VOYAGE_API_KEY is not set — add it to backend/.env "
                "(read through config.py only; never pass it on a command line)"
            )
        self._client = httpx.Client(
            base_url=_VOYAGE_BASE_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=settings.embed_request_timeout_seconds,
            transport=transport,
        )
        self._model = settings.embedding_model
        self._dims = settings.embedding_dims

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        self._client.close()

    def embed(self, texts: list[str]) -> BatchEmbedding:
        response = self._client.post(
            "/embeddings",
            json={
                "model": self._model,
                "input": texts,
                "input_type": "document",
                "output_dimension": self._dims,
            },
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientEmbeddingError(
                f"HTTP {response.status_code} from embeddings API",
                retry_after=_parse_retry_after(response.headers.get("retry-after")),
            )
        response.raise_for_status()
        payload = response.json()
        return BatchEmbedding(
            vectors=[item["embedding"] for item in payload["data"]],
            total_tokens=payload["usage"]["total_tokens"],
        )


@dataclass
class EmbedStats:
    chunks_total: int = 0
    already_embedded: int = 0
    embedded: int = 0
    batches: int = 0
    tokens_billed: int = 0
    usd: float = 0.0
    estimated_tokens: int = 0
    estimated_usd: float = 0.0
    merged: bool = False


def _read_chunks(chunks_path: Path) -> list[ChunkText]:
    chunks: list[ChunkText] = []
    with chunks_path.open(encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            chunks.append(
                ChunkText(
                    chunk_id=record["chunk_id"],
                    text=record["text"],
                    n_tokens=record["n_tokens"],
                )
            )
    return chunks


def _existing_chunk_ids(vectors_path: Path, shards_dir: Path) -> set[str]:
    done: set[str] = set()
    for f in [vectors_path, *sorted(shards_dir.glob("*.parquet"))]:
        if f.exists():
            done.update(pq.read_table(f, columns=["chunk_id"])["chunk_id"].to_pylist())
    return done


def _batches(chunks: list[ChunkText], max_items: int, max_tokens: int) -> list[list[ChunkText]]:
    batches: list[list[ChunkText]] = []
    current: list[ChunkText] = []
    current_tokens = 0
    for chunk in chunks:
        if current and (len(current) >= max_items or current_tokens + chunk.n_tokens > max_tokens):
            batches.append(current)
            current, current_tokens = [], 0
        current.append(chunk)
        current_tokens += chunk.n_tokens
    if current:
        batches.append(current)
    return batches


def _vectors_table(chunk_ids: list[str], vectors: list[list[float]], dims: int) -> pa.Table:
    flat = pa.array([value for vector in vectors for value in vector], type=pa.float32())
    vector_array = pa.FixedSizeListArray.from_arrays(flat, dims)
    return pa.table({"chunk_id": pa.array(chunk_ids, type=pa.string()), "vector": vector_array})


def _write_parquet_atomic(path: Path, table: pa.Table) -> None:
    # Same crash contract as extract_pdfs: a killed run never leaves a
    # half-written file that a resume would trust.
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)


def _embed_with_retry(
    backend: EmbeddingsBackend,
    texts: list[str],
    max_attempts: int,
    base_seconds: float,
) -> BatchEmbedding:
    for attempt in range(max_attempts):
        try:
            return backend.embed(texts)
        except _RETRYABLE as exc:
            if attempt == max_attempts - 1:
                raise EmbeddingError(
                    f"batch still failing after {max_attempts} attempts: {type(exc).__name__}"
                ) from exc
            # Exponential backoff, but never shorter than the server's ask —
            # free-tier throttling must never turn into a retry storm.
            wait = base_seconds * 2**attempt
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                wait = max(wait, retry_after)
            _log.warning(
                f"retryable API error ({type(exc).__name__}), attempt "
                f"{attempt + 1}/{max_attempts}, backing off {wait:.0f}s"
            )
            time.sleep(wait)
    raise AssertionError("unreachable: the last attempt re-raises inside the loop")


def _merge_shards(vectors_path: Path, shards_dir: Path) -> None:
    """Everything embedded -> one vectors.parquet; dedupe guards the
    crash-between-merge-and-cleanup window (both copies briefly exist)."""
    sources = [vectors_path, *sorted(shards_dir.glob("*.parquet"))]
    parts = [pq.read_table(f) for f in sources if f.exists()]
    merged = pa.concat_tables(parts)
    seen: set[str] = set()
    keep: list[int] = []
    for i, chunk_id in enumerate(merged["chunk_id"].to_pylist()):
        if chunk_id not in seen:
            seen.add(chunk_id)
            keep.append(i)
    if len(keep) < merged.num_rows:
        merged = merged.take(keep)
    _write_parquet_atomic(vectors_path, merged)
    for f in shards_dir.glob("*.parquet"):
        f.unlink()
    if shards_dir.exists() and not any(shards_dir.iterdir()):
        shards_dir.rmdir()


def run(
    chunks_path: Path,
    vectors_path: Path,
    shards_dir: Path,
    backend: EmbeddingsBackend | None,
    *,
    dims: int,
    batch_max_items: int,
    batch_max_tokens: int,
    usd_per_mtok: float,
    retry_max_attempts: int,
    retry_base_seconds: float,
    limit: int | None = None,
    estimate: bool = False,
) -> EmbedStats:
    """Embed every not-yet-embedded chunk; merge to vectors.parquet when done."""
    tracer = telemetry.get_tracer("askrag.ingest")
    stats = EmbedStats()
    chunks = _read_chunks(chunks_path)
    stats.chunks_total = len(chunks)
    done = _existing_chunk_ids(vectors_path, shards_dir)
    todo = [c for c in chunks if c.chunk_id not in done]
    stats.already_embedded = stats.chunks_total - len(todo)
    # --limit applies before the estimate so --estimate --limit N prices
    # exactly the run it gates, not the whole backlog.
    deferred = 0
    if limit is not None:
        deferred = max(len(todo) - limit, 0)
        todo = todo[:limit]
    stats.estimated_tokens = sum(c.n_tokens for c in todo)
    stats.estimated_usd = stats.estimated_tokens / 1e6 * usd_per_mtok

    if estimate:
        _log.info(
            f"estimate: {len(todo)} chunks to embed ({stats.already_embedded} already done, "
            f"{deferred} beyond --limit), ~{stats.estimated_tokens:,} tokens, "
            f"~${stats.estimated_usd:.2f} at ${usd_per_mtok}/Mtok",
            extra={"askrag_extra": {"askrag.estimated_tokens": stats.estimated_tokens}},
        )
        return stats

    if backend is None:
        raise EmbeddingError("a backend is required unless estimate=True")

    with tracer.start_as_current_span("askrag.ingest.embed") as run_span:
        shard_seq = len(list(shards_dir.glob("*.parquet")))
        for batch in _batches(todo, batch_max_items, batch_max_tokens):
            with tracer.start_as_current_span("askrag.ingest.embed.batch") as batch_span:
                result = _embed_with_retry(
                    backend,
                    [c.text for c in batch],
                    retry_max_attempts,
                    retry_base_seconds,
                )
                if len(result.vectors) != len(batch) or any(len(v) != dims for v in result.vectors):
                    raise EmbeddingError(
                        f"API returned {len(result.vectors)} vectors "
                        f"(expected {len(batch)}) or wrong dims (expected {dims})"
                    )
                shards_dir.mkdir(parents=True, exist_ok=True)
                shard = shards_dir / f"shard_{shard_seq:06d}.parquet"
                _write_parquet_atomic(
                    shard, _vectors_table([c.chunk_id for c in batch], result.vectors, dims)
                )
                shard_seq += 1
                stats.batches += 1
                stats.embedded += len(batch)
                stats.tokens_billed += result.total_tokens
                stats.usd = stats.tokens_billed / 1e6 * usd_per_mtok
                batch_span.set_attribute("askrag.items", len(batch))
                batch_span.set_attribute("askrag.tokens", result.total_tokens)
            _log.info(
                f"embedded {stats.already_embedded + stats.embedded}/{stats.chunks_total} "
                f"chunks, {stats.tokens_billed:,} tokens, ${stats.usd:.4f} so far"
            )

        # Merge only when the corpus is fully embedded (a --limit smoke run
        # leaves its shards for the next resume) and there are shards to fold
        # in — including leftovers from a crash between merge and cleanup.
        if deferred == 0 and any(shards_dir.glob("*.parquet")):
            _merge_shards(vectors_path, shards_dir)
            stats.merged = True

        run_span.set_attribute("askrag.chunks_total", stats.chunks_total)
        run_span.set_attribute("askrag.already_embedded", stats.already_embedded)
        run_span.set_attribute("askrag.embedded", stats.embedded)
        run_span.set_attribute("askrag.batches", stats.batches)
        run_span.set_attribute("askrag.tokens_billed", stats.tokens_billed)
        run_span.set_attribute("askrag.usd", round(stats.usd, 6))
        run_span.set_attribute("askrag.merged", stats.merged)

    _log.info(
        f"embed_chunks: {stats.embedded} embedded ({stats.already_embedded} already done) "
        f"in {stats.batches} batches; {stats.tokens_billed:,} tokens, ${stats.usd:.4f}; "
        f"merged={stats.merged} -> {vectors_path if stats.merged else shards_dir}"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="sum stored n_tokens and price the run (honors --limit); no API key, no network",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="embed at most N pending chunks (smoke runs)"
    )
    args = parser.parse_args(argv)
    try:
        with contextlib.ExitStack() as stack:
            backend = None if args.estimate else stack.enter_context(VoyageEmbeddings(settings))
            run(
                chunks_path=settings.chunks_jsonl_path,
                vectors_path=settings.vectors_parquet_path,
                shards_dir=settings.vectors_shards_dir,
                backend=backend,
                dims=settings.embedding_dims,
                batch_max_items=settings.embed_batch_max_items,
                batch_max_tokens=settings.embed_batch_max_tokens,
                usd_per_mtok=settings.embedding_usd_per_mtok,
                retry_max_attempts=settings.embed_retry_max_attempts,
                retry_base_seconds=settings.embed_retry_base_seconds,
                limit=args.limit,
                estimate=args.estimate,
            )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
