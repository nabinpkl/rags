"""Per-stage ingest report: counts + snapshot datestamp (D12). Read-only.

Deliberately MINIMAL (vertical-slice directive, issue #14): each pipeline
stage's artifact is counted as it exists on disk right now, plus the corpus
snapshot stamp build_indexes wrote. No history, no dashboards — those are
explicitly deferred.
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
import chromadb.config
import chromadb.errors
import pyarrow.parquet as pq

from askrag.config import Settings, get_settings


@dataclass
class IngestStats:
    """Counts per pipeline stage; None = that stage's artifact is absent."""

    papers_collected: int | None = None
    papers_extracted: int | None = None
    skiplisted: int | None = None
    skip_reasons: dict[str, int] = field(default_factory=dict)
    chunks: int | None = None
    chunk_papers: int | None = None
    vectors: int | None = None
    model_slug: str | None = None
    corpus_db_papers: int | None = None
    corpus_db_chunks: int | None = None
    chroma_count: int | None = None
    snapshot: str | None = None
    built_at: str | None = None


def _count_arxiv_db(path: Path) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT count(*) FROM papers").fetchone()[0]
    finally:
        conn.close()


def collect(settings: Settings) -> IngestStats:
    stats = IngestStats()
    stats.papers_collected = _count_arxiv_db(settings.arxiv_db_path)

    if settings.extracted_dir.exists():
        stats.papers_extracted = sum(1 for _ in settings.extracted_dir.glob("*.json"))

    if settings.skiplist_path.exists():
        skiplist = json.loads(settings.skiplist_path.read_text(encoding="utf-8"))
        stats.skiplisted = len(skiplist)
        stats.skip_reasons = dict(Counter(entry["reason"] for entry in skiplist.values()))

    if settings.chunks_jsonl_path.exists():
        paper_ids: set[str] = set()
        n = 0
        with settings.chunks_jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                paper_ids.add(json.loads(line)["paper_id"])
                n += 1
        stats.chunks, stats.chunk_papers = n, len(paper_ids)

    if settings.vectors_parquet_path.exists():
        stats.vectors = pq.read_metadata(settings.vectors_parquet_path).num_rows
        stats.model_slug = settings.embedding_model_slug

    if settings.corpus_db_path.exists():
        conn = sqlite3.connect(f"{settings.corpus_db_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            stats.corpus_db_papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
            stats.corpus_db_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
            stats.snapshot, stats.built_at = meta.get("snapshot"), meta.get("built_at")
        finally:
            conn.close()

    if settings.chroma_dir.exists():
        client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            # Deliberate no-egress, not an accident of the 1.5.9 pin (whose
            # telemetry client happens to be a no-op stub — review #55).
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        try:
            stats.chroma_count = client.get_collection(settings.embedding_model_slug).count()
        except chromadb.errors.NotFoundError:  # not built yet — absent, not a crash
            stats.chroma_count = None

    return stats


def report(stats: IngestStats) -> str:
    def fmt(value: int | str | None) -> str:
        return "—" if value is None else f"{value:,}" if isinstance(value, int) else value

    lines = [
        f"corpus snapshot: {fmt(stats.snapshot)} (built {fmt(stats.built_at)})",
        f"collect : {fmt(stats.papers_collected)} papers (arxiv.db)",
        f"extract : {fmt(stats.papers_extracted)} extracted, {fmt(stats.skiplisted)} skiplisted",
    ]
    for reason, count in sorted(stats.skip_reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"          skip: {count} × {reason}")
    lines += [
        f"chunk   : {fmt(stats.chunks)} chunks over {fmt(stats.chunk_papers)} papers",
        f"embed   : {fmt(stats.vectors)} vectors ({fmt(stats.model_slug)})",
        f"index   : corpus.db {fmt(stats.corpus_db_papers)} papers / "
        f"{fmt(stats.corpus_db_chunks)} chunks; chroma {fmt(stats.chroma_count)}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    print(report(collect(get_settings())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
