import json
import sqlite3

import numpy as np
import pytest

from askrag.config import Settings
from askrag.ingest.embed_chunks import BatchEmbedding, EmbeddingError
from askrag.paper_map import embed_abstracts as ea


def _db(path, rows):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE papers (arxiv_id TEXT, title TEXT, abstract TEXT)")
    db.executemany("INSERT INTO papers VALUES (?, ?, ?)", rows)
    db.commit()
    db.close()


def test_paper_text_joins_title_and_collapsed_abstract():
    assert ea.paper_text(" A Title ", "line one\n  line two") == "A Title. line one line two"


def test_select_papers_scopes_by_id_month_and_orders(tmp_path):
    db = tmp_path / "corpus.db"
    _db(db, [("2608.00002", "B", "b"), ("2606.00001", "Old", "o"), ("2607.00001", "A", "a")])
    got = ea.select_papers(db, "2607")
    assert [a for a, _ in got] == ["2607.00001", "2608.00002"]


def test_missing_keeps_wanted_order():
    cache = {"b": np.zeros(2)}
    assert ea.missing(cache, ["c", "b", "a"]) == ["c", "a"]


def test_load_cache_rejects_row_count_mismatch(tmp_path):
    s = Settings(corpus_dir=tmp_path)
    vec, ids = ea.cache_paths(s)
    vec.parent.mkdir(parents=True)
    np.save(vec, np.zeros((2, 3), dtype=np.float32))
    ids.write_text(json.dumps(["a"]))
    with pytest.raises(ValueError, match="2 rows for 1 ids"):
        ea.load_cache(s)


def test_embed_abstracts_reuses_cache_without_a_provider(tmp_path):
    s = Settings(corpus_dir=tmp_path)
    _db(s.corpus_db_path, [("2607.00001", "A", "a"), ("2607.00002", "B", "b")])
    vec, ids = ea.cache_paths(s)
    vec.parent.mkdir(parents=True)
    np.save(vec, np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32))
    ids.write_text(json.dumps(["2607.00001", "2607.00002"]))
    got_ids, x = ea.embed_abstracts(s)
    assert got_ids == ["2607.00001", "2607.00002"]
    np.testing.assert_allclose(x, [[0.6, 0.8], [0.0, 1.0]], rtol=1e-6)


def test_a_failed_run_keeps_the_batches_it_finished(tmp_path, monkeypatch):
    s = Settings(corpus_dir=tmp_path, paper_map_embed_batch=1)
    _db(s.corpus_db_path, [("2607.00001", "A", "a"), ("2607.00002", "B", "b")])

    class Backend:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    calls = []

    def embed(_backend, texts, *_args):
        calls.append(texts)
        if len(calls) == 2:
            raise EmbeddingError("provider down")
        return BatchEmbedding(vectors=[[1.0, 0.0]], total_tokens=3, usd=0.0)

    monkeypatch.setattr(ea, "OpenRouterEmbeddings", Backend)
    monkeypatch.setattr(ea, "_embed_splitting", embed)
    with pytest.raises(EmbeddingError):
        ea.embed_abstracts(s)
    assert list(ea.load_cache(s)) == ["2607.00001"]
