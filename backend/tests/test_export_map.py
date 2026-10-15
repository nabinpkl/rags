import json

import numpy as np
import pytest

from askrag.paper_map.export_map import FORMAT_VERSION, Theme, quantize, write_map


def test_quantize_spans_the_full_uint16_range():
    qx, qy, bounds = quantize(np.array([[-1.0, 10.0], [3.0, 12.0], [1.0, 11.0]]))
    assert qx.tolist() == [0, 65535, 32768]
    assert qy.tolist() == [0, 65535, 32768]
    assert bounds == [-1.0, 10.0, 3.0, 12.0]


def test_write_map_round_trips_points_and_meta(tmp_path):
    xy = np.array([[0.0, 0.0], [1.0, 2.0], [0.5, 1.0]])
    write_map(
        tmp_path,
        ids=["2607.00001", "2607.00002", "2609.00003"],
        versions=["v1", "v2", "v1"],
        titles=["A", "B", "C"],
        xy=xy,
        theme_index=np.array([0, -1, 0]),
        themes=[Theme(0, "robot · arm", 2, 0.25, 0.5, "cs.RO")],
    )
    raw = (tmp_path / "points.bin").read_bytes()
    assert len(raw) == 3 * 2 + 3 * 2 + 3 * 2
    qx = np.frombuffer(raw[:6], "<u2")
    themes = np.frombuffer(raw[12:], "<i2")
    assert qx.tolist() == [0, 65535, 32768]
    assert themes.tolist() == [0, -1, 0]
    meta = json.loads((tmp_path / "map.json").read_text())
    assert meta["version"] == FORMAT_VERSION
    assert len(meta["digest"]) == 16
    assert meta["n"] == 3 and meta["unthemed"] == 1
    assert (meta["from_month"], meta["to_month"]) == ("2607", "2609")
    assert meta["themes"][0]["name"] == "robot · arm"
    papers = json.loads((tmp_path / "papers.json").read_text())
    assert papers["versions"] == ["v1", "v2", "v1"]


def test_write_map_rejects_mismatched_lengths(tmp_path):
    with pytest.raises(ValueError, match="differ in length"):
        write_map(
            tmp_path,
            ids=["a"],
            versions=[],
            titles=["A"],
            xy=np.zeros((1, 2)),
            theme_index=np.zeros(1),
            themes=[],
        )


def test_digest_changes_when_the_points_do(tmp_path):
    def build(xy):
        write_map(
            tmp_path,
            ids=["2607.00001", "2607.00002", "2607.00003"],
            versions=["v1", "v1", "v1"],
            titles=["A", "B", "C"],
            xy=np.array(xy),
            theme_index=np.array([0, -1, 0]),
            themes=[Theme(0, "t", 2, 0.0, 0.0, "cs.RO")],
        )
        return json.loads((tmp_path / "map.json").read_text())["digest"]

    assert build([[0, 0], [1, 1], [0.5, 0.5]]) != build([[0, 0], [1, 1], [0.2, 0.7]])
