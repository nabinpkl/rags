"""UMAP layouts of the abstract vectors: 10-d to cluster in, 2-d to draw.

Each layout is cached under a key of the ids and every parameter, so a rerun
over the same papers is free and a changed scope or setting recomputes.
"""

import hashlib
import json
from pathlib import Path

import numpy as np


def cache_key(ids: list[str], **params: object) -> str:
    h = hashlib.sha256(json.dumps([ids, sorted(params.items())]).encode())
    return h.hexdigest()[:16]


def layout(
    x: np.ndarray,
    ids: list[str],
    cache_dir: Path,
    *,
    dims: int,
    neighbors: int,
    min_dist: float,
    seed: int,
) -> np.ndarray:
    key = cache_key(ids, dims=dims, neighbors=neighbors, min_dist=min_dist, seed=seed)
    path = cache_dir / f"layout_{dims}d_{key}.npy"
    if path.exists():
        return np.load(path)
    import umap  # the map dependency group only; the API image never loads it

    z = umap.UMAP(
        n_components=dims,
        n_neighbors=neighbors,
        min_dist=min_dist,
        metric="cosine",
        random_state=seed,
    ).fit_transform(x)
    z = np.asarray(z, dtype=np.float32)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(path, z)
    return z
