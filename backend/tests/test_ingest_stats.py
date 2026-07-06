"""Tests for askrag.ingest.ingest_stats — the per-stage count report."""

import json
import sqlite3

import pytest

from askrag.config import Settings
from askrag.ingest import ingest_stats


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        corpus_dir=tmp_path / "corpus",
        embedding_model="fake/fake-embed",
        embedding_dims=4,
    )


def test_absent_artifacts_report_none_not_crash(settings):
    stats = ingest_stats.collect(settings)
    assert stats.papers_collected is None
    assert stats.chunks is None
    assert stats.corpus_db_papers is None
    assert "—" in ingest_stats.report(stats)


def test_counts_per_stage(settings):
    corpus = settings.corpus_dir
    corpus.mkdir(parents=True)

    conn = sqlite3.connect(settings.arxiv_db_path)
    conn.execute("CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO papers VALUES (?)", [("a",), ("b",), ("c",)])
    conn.commit()
    conn.close()

    settings.extracted_dir.mkdir()
    (settings.extracted_dir / "a.json").write_text("{}")
    (settings.extracted_dir / "b.json").write_text("{}")

    settings.skiplist_path.write_text(
        json.dumps({"c": {"pdf": "c.pdf", "reason": "encrypted", "failed_at": "t"}})
    )

    with settings.chunks_jsonl_path.open("w") as fh:
        for cid, pid in [("a#0", "a"), ("a#1", "a"), ("b#0", "b")]:
            fh.write(json.dumps({"chunk_id": cid, "paper_id": pid}) + "\n")

    stats = ingest_stats.collect(settings)
    assert stats.papers_collected == 3
    assert stats.papers_extracted == 2
    assert stats.skiplisted == 1
    assert stats.skip_reasons == {"encrypted": 1}
    assert stats.chunks == 3
    assert stats.chunk_papers == 2


def test_snapshot_stamp_read_from_corpus_db(settings):
    settings.corpus_dir.mkdir(parents=True)
    conn = sqlite3.connect(settings.corpus_db_path)
    conn.executescript(
        """
        CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY);
        CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO papers VALUES ('a');
        INSERT INTO chunks VALUES ('a#0');
        INSERT INTO meta VALUES ('built_at', '2026-07-05T21:00:00+00:00');
        INSERT INTO meta VALUES ('snapshot', '2026-07');
        """
    )
    conn.commit()
    conn.close()

    stats = ingest_stats.collect(settings)
    assert stats.corpus_db_papers == 1
    assert stats.corpus_db_chunks == 1
    assert stats.snapshot == "2026-07"
    report = ingest_stats.report(stats)
    assert "corpus snapshot: 2026-07" in report
