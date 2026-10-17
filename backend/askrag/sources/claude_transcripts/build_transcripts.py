"""`just transcripts`: Claude Code session logs -> the transcripts index (D21).

Read the logs, redact secrets and email addresses, chunk by turns, embed with
the corpus embedder, and build the index pair with the same core every source
uses (retrieval/embed_chunks.py, retrieval/build_index.py). Outputs land in
`corpus/sources/claude_transcripts/`: chunks.jsonl, the vectors parquet,
index.db and chroma/. Nothing here is served: the deploy mounts none of it.

Embedding is incremental by content: each chunk's text hash is kept beside
the vectors, and a chunk whose text changed since the last build (a session
that grew) loses its old vector and is embedded again. `--dry-run` reads,
redacts and chunks, prints the counts, and writes nothing.
"""

import argparse
import contextlib
import hashlib
import json
import logging
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq
import tiktoken

from askrag import telemetry
from askrag.config import Settings, get_settings
from askrag.retrieval import embed_chunks
from askrag.retrieval.build_index import IndexChunk, IndexDocument, build_index
from askrag.sources.claude_transcripts import source
from askrag.sources.claude_transcripts.chunk_sessions import chunk_session, document_of
from askrag.sources.claude_transcripts.read_sessions import Session, read_sessions
from askrag.sources.claude_transcripts.redact_secrets import redact

_log = logging.getLogger("askrag.sources.claude_transcripts.build_transcripts")


def redact_sessions(sessions: list[Session]) -> Counter[str]:
    """Redact every prompt, line and title in place; the per-kind counts."""
    total: Counter[str] = Counter()
    for session in sessions:
        session.title, counts = redact(session.title)
        total += counts
        for turn in session.turns:
            turn.prompt, counts = redact(turn.prompt)
            total += counts
            redacted = []
            for line in turn.lines:
                line, counts = redact(line)
                total += counts
                redacted.append(line)
            turn.lines = redacted
    return total


@lru_cache(maxsize=1)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def token_tools(encoding_name: str) -> tuple[Callable[[str], int], Callable[[str, int], list[str]]]:
    enc = _encoding(encoding_name)

    def count(text: str) -> int:
        return len(enc.encode(text, disallowed_special=()))

    def split(text: str, max_tokens: int) -> list[str]:
        tokens = enc.encode(text, disallowed_special=())
        return [enc.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]

    return count, split


def chunk_all(
    sessions: list[Session], settings: Settings
) -> tuple[list[IndexDocument], list[IndexChunk]]:
    count, split = token_tools(settings.tokenizer_encoding)
    documents = [document_of(s) for s in sessions]
    chunks = [
        c for s in sessions for c in chunk_session(s, count, split, settings.chunk_size_tokens)
    ]
    return documents, chunks


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def drop_stale_vectors(vectors_path: Path, hashes_path: Path, chunks: list[IndexChunk]) -> int:
    """Remove vectors whose chunk is gone or whose text changed; how many."""
    current = {c.chunk_id: _text_hash(c.text) for c in chunks}
    if not vectors_path.exists():
        return 0
    previous = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
    table = pq.read_table(vectors_path)
    ids = table["chunk_id"].to_pylist()
    keep = [n for n, i in enumerate(ids) if i in current and previous.get(i) == current[i]]
    if len(keep) == len(ids):
        return 0
    filtered = table.take(keep)
    filtered = filtered.replace_schema_metadata(table.schema.metadata)
    tmp = vectors_path.with_suffix(".tmp")
    pq.write_table(filtered, tmp)
    tmp.replace(vectors_path)
    return len(ids) - len(keep)


def write_chunks_jsonl(path: Path, chunks: list[IndexChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(asdict(c)) + "\n" for c in chunks))
    tmp.replace(path)


def run(settings: Settings, *, dry_run: bool = False) -> dict[str, int]:
    local = source.search_settings(settings)
    sessions = read_sessions(settings.transcripts_root, settings.transcripts_tool_input_chars)
    redactions = redact_sessions(sessions)
    documents, chunks = chunk_all(sessions, settings)
    stats = {
        "sessions": len(sessions),
        "turns": sum(len(s.turns) for s in sessions),
        "chunks": len(chunks),
        "tokens": sum(c.n_tokens for c in chunks),
        "redactions": sum(redactions.values()),
    }
    _log.info(f"transcripts: {stats}; redactions by kind {dict(sorted(redactions.items()))}")
    if dry_run:
        return stats

    out = settings.transcripts_dir
    chunks_path = out / "chunks.jsonl"
    vectors_path = out / "vectors" / f"{local.embedding_model_slug}.parquet"
    shards_dir = out / "vectors" / f"{local.embedding_model_slug}_shards"
    hashes_path = out / "vectors" / "chunk_hashes.json"
    write_chunks_jsonl(chunks_path, chunks)
    stats["vectors_dropped"] = drop_stale_vectors(vectors_path, hashes_path, chunks)

    batch_max_items, batch_max_tokens = local.embed_batch_limits
    with contextlib.ExitStack() as stack:
        backend = stack.enter_context(embed_chunks.make_backend(local))
        embedded = embed_chunks.run(
            chunks_path=chunks_path,
            vectors_path=vectors_path,
            shards_dir=shards_dir,
            backend=backend,
            provenance=embed_chunks.EmbeddingProvenance.from_settings(local),
            dims=local.embedding_dims,
            batch_max_items=batch_max_items,
            batch_max_tokens=batch_max_tokens,
            usd_per_mtok=local.embedding_usd_per_mtok,
            retry_max_attempts=local.embed_retry_max_attempts,
            retry_base_seconds=local.embed_retry_base_seconds,
            tokens_per_minute=local.embed_tokens_per_minute,
        )
    stats["embedded"] = embedded.embedded
    hashes_path.write_text(json.dumps({c.chunk_id: _text_hash(c.text) for c in chunks}))

    table = embed_chunks.read_vectors(vectors_path, expected_slug=local.embedding_model_slug)
    stats["indexed"] = build_index(
        source.index(settings),
        documents,
        chunks,
        table["chunk_id"].to_pylist(),
        table["vector"].to_pylist(),
        add_batch_size=settings.chroma_add_batch_size,
    )
    _log.info(f"transcripts index built: {stats}")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="count and redact; write nothing")
    args = parser.parse_args(argv)
    settings = get_settings()
    telemetry.init(settings)
    try:
        print(json.dumps(run(settings, dry_run=args.dry_run)))
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
