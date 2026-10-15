import numpy as np

from askrag.paper_map.layout_papers import cache_key, layout


def test_cache_key_changes_with_ids_and_params():
    base = cache_key(["a", "b"], dims=2, seed=7)
    assert base == cache_key(["a", "b"], seed=7, dims=2)
    assert base != cache_key(["a", "c"], dims=2, seed=7)
    assert base != cache_key(["a", "b"], dims=10, seed=7)
    assert base != cache_key(["a", "b"], dims=2, seed=None)


def test_layout_returns_the_cached_file(tmp_path):
    ids = ["a", "b"]
    params = {"dims": 2, "neighbors": 30, "min_dist": 0.1, "seed": 7}
    cached = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    np.save(tmp_path / f"layout_2d_{cache_key(ids, **params)}.npy", cached)
    got = layout(np.zeros((2, 4), dtype=np.float32), ids, tmp_path, **params)
    np.testing.assert_array_equal(got, cached)
