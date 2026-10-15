"""Title + abstract vectors for every catalog paper in the map's scope.

The cache is two files keyed by the embedding model slug: the vectors and the
ids they belong to, row for row. A run embeds only the ids the cache lacks, so
a new month costs only its own papers. One model per cache file, so two
models' vectors can never share a matrix (the D5 provenance rule).
"""

import json
import logging
import sqlite3
from pathlib import Path

import numpy as np

from askrag.config import Settings
from askrag.ingest.embed_chunks import OpenRouterEmbeddings, _embed_splitting

_log = logging.getLogger("askrag.paper_map.embed_abstracts")


def paper_text(title: str, abstract: str) -> str:
    return f"{title.strip()}. {' '.join(abstract.split())}"


def select_papers(db_path: Path, from_month: str) -> list[tuple[str, str]]:
    """(arxiv_id, text) for papers whose id month is `from_month` or later, by id."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT arxiv_id, title, abstract FROM papers "
            "WHERE substr(arxiv_id, 1, 4) >= ? ORDER BY arxiv_id",
            (from_month,),
        ).fetchall()
    finally:
        db.close()
    return [(a, paper_text(t, ab)) for a, t, ab in rows]


def cache_paths(settings: Settings) -> tuple[Path, Path]:
    slug = settings.embedding_model_slug
    d = settings.paper_map_dir
    return d / f"vectors_{slug}.npy", d / f"ids_{slug}.json"


def load_cache(settings: Settings) -> dict[str, np.ndarray]:
    vec_path, ids_path = cache_paths(settings)
    if not vec_path.exists():
        return {}
    ids = json.loads(ids_path.read_text())
    vecs = np.load(vec_path)
    if len(ids) != len(vecs):
        raise ValueError(f"{vec_path.name} has {len(vecs)} rows for {len(ids)} ids")
    return dict(zip(ids, vecs, strict=True))


def missing(cache: dict[str, np.ndarray], wanted: list[str]) -> list[str]:
    return [i for i in wanted if i not in cache]


def save_cache(settings: Settings, cache: dict[str, np.ndarray]) -> None:
    vec_path, ids_path = cache_paths(settings)
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted(cache)
    np.save(vec_path, np.stack([cache[k] for k in keys]))
    ids_path.write_text(json.dumps(keys))


# Batches between cache writes: a run that dies keeps what it paid for.
_SAVE_EVERY = 20


def embed_abstracts(settings: Settings) -> tuple[list[str], np.ndarray]:
    """Ids in scope and their vectors, unit-normalised, embedding only what is new."""
    papers = select_papers(settings.corpus_db_path, settings.paper_map_from_month)
    if not papers:
        raise ValueError(f"no papers from month {settings.paper_map_from_month}")
    cache = load_cache(settings)
    todo = missing(cache, [a for a, _ in papers])
    if todo:
        text = dict(papers)
        usd, tokens, unsaved = 0.0, 0, 0
        batch = settings.paper_map_embed_batch
        try:
            with OpenRouterEmbeddings(settings) as backend:
                for i in range(0, len(todo), batch):
                    ids = todo[i : i + batch]
                    r = _embed_splitting(
                        backend,
                        [text[a] for a in ids],
                        settings.embed_retry_max_attempts,
                        settings.embed_retry_base_seconds,
                    )
                    cache.update(zip(ids, np.asarray(r.vectors, dtype=np.float32), strict=True))
                    tokens += r.total_tokens
                    usd += r.usd or 0.0
                    unsaved += 1
                    if unsaved == _SAVE_EVERY:
                        save_cache(settings, cache)
                        unsaved = 0
                        _log.info(f"embedded {i + len(ids)}/{len(todo)}, ${usd:.4f}")
        finally:
            if unsaved:
                save_cache(settings, cache)
        _log.info(f"embedded {len(todo)} papers, {tokens} tokens, ${usd:.4f}")
    ids = [a for a, _ in papers]
    x = np.stack([cache[a] for a in ids]).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return ids, x
