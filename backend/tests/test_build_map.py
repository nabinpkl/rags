import json
import sqlite3

import numpy as np

from askrag.config import Settings
from askrag.paper_map import build_map


def test_run_orders_themes_by_size_and_exports(tmp_path, monkeypatch):
    s = Settings(
        corpus_dir=tmp_path,
        paper_map_min_cluster_size=10,
        paper_map_min_samples=5,
        paper_map_themes_per_group=2,
    )
    ids = [f"2607.{i:05d}" for i in range(91)]
    db = sqlite3.connect(s.corpus_db_path)
    db.execute(
        "CREATE TABLE papers (arxiv_id TEXT, title TEXT, abstract TEXT, version TEXT, "
        "primary_category TEXT)"
    )
    rows = [(a, "robot arm grasping", "robot arm", "v1", "cs.RO") for a in ids[:50]]
    rows += [(a, "speech audio", "speech speaker", "v2", "cs.SD") for a in ids[50:90]]
    rows += [(ids[90], "lonely", "outlier", "v1", "cs.LG")]
    db.executemany("INSERT INTO papers VALUES (?, ?, ?, ?, ?)", rows)
    db.commit()
    db.close()

    rng = np.random.default_rng(0)
    pts = np.vstack([rng.normal(0, 0.1, (50, 2)), rng.normal(5, 0.1, (40, 2)), [[20, -20]]])
    monkeypatch.setattr(build_map, "embed_abstracts", lambda _s, _from: (ids, pts))
    monkeypatch.setattr(build_map, "layout", lambda x, *_a, **_k: x)
    build_map.run(s, "recent")

    meta = json.loads((s.paper_map_dir / "recent" / "map.json").read_text())
    assert [t["size"] for t in meta["themes"]] == [50, 40]
    assert meta["themes"][0]["top_category"] == "cs.RO"
    assert meta["unthemed"] == 1
    assert len(meta["groups"]) == 1
    assert {t["group"] for t in meta["themes"]} == {0}
    raw = (s.paper_map_dir / "recent" / "points.bin").read_bytes()
    themes = np.frombuffer(raw[4 * 91 :], "<i2")
    assert themes[0] == 0 and themes[60] == 1 and themes[90] == -1
