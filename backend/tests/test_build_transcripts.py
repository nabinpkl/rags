"""Tests for askrag.sources.claude_transcripts.build_transcripts — synthetic
logs, a fake embedder, a real index at the end."""

import json

import pytest

from askrag.config import Settings
from askrag.retrieval import embed_chunks
from askrag.retrieval.embed_chunks import BatchEmbedding
from askrag.retrieval.hybrid_search import HybridSearch
from askrag.sources.claude_transcripts import build_transcripts, source

FAKE_KEY = "sk-or-v1-" + "Z9y8X7w6V5u4T3s2R1q0" * 2


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def write_log(root, sid, prompts):
    path = root / "-w-rags" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in prompts:
        base = {"sessionId": sid, "timestamp": "2026-10-02T00:00:00Z", "cwd": "/w/rags"}
        lines.append({**base, "type": "user", "message": {"content": p}})
        lines.append(
            {**base, "type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}
        )
    path.write_text("".join(json.dumps(r) + "\n" for r in lines))


class FakeBackend:
    def __init__(self):
        self.texts: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def embed(self, texts):
        self.texts.extend(texts)
        return BatchEmbedding(
            [[1.0, 0.0] if "caddy" in t else [0.0, 1.0] for t in texts], total_tokens=0, usd=0.0
        )


@pytest.fixture
def settings(tmp_path):
    root = tmp_path / "logs"
    write_log(root, "aaa", ["why does caddy 404 the map", f"my key is {FAKE_KEY}"])
    write_log(root, "bbb", ["label collisions in deck.gl"])
    return Settings(corpus_dir=tmp_path / "corpus", transcripts_root=root, embedding_dims=2)


def test_dry_run_counts_and_writes_nothing(settings):
    stats = build_transcripts.run(settings, dry_run=True)
    assert stats == {
        "sessions": 2,
        "turns": 3,
        "chunks": 2,
        "tokens": stats["tokens"],
        "redactions": 1,
    }
    assert not settings.transcripts_dir.exists()


def test_a_build_redacts_embeds_and_indexes_and_a_rebuild_reembeds_only_changes(
    settings, monkeypatch
):
    backend = FakeBackend()
    monkeypatch.setattr(embed_chunks, "make_backend", lambda s, **_: backend)
    stats = build_transcripts.run(settings)
    assert (stats["chunks"], stats["embedded"], stats["indexed"]) == (2, 2, 2)
    assert all(FAKE_KEY not in t for t in backend.texts)
    stored = (settings.transcripts_dir / "chunks.jsonl").read_text()
    assert FAKE_KEY not in stored and "[redacted:api_key]" in stored

    again = build_transcripts.run(settings)
    assert (again["vectors_dropped"], again["embedded"]) == (0, 0)

    write_log(settings.transcripts_root, "bbb", ["label collisions in deck.gl", "and on zoom"])
    grown = build_transcripts.run(settings)
    assert (grown["vectors_dropped"], grown["embedded"]) == (1, 1)

    local = source.search_settings(settings)

    class Embedder:
        def embed_query_priced(self, text):
            return [1.0, 0.0], None

    hits = HybridSearch(local, source.index(settings), embedder=Embedder()).search("caddy", k=1)
    assert hits[0].doc_id == "aaa"
