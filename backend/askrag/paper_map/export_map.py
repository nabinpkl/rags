"""Write the map the /map page reads: points.bin, map.json, papers.json.

points.bin is three little-endian arrays back to back, each n long: x and y
as uint16 over the bounds in map.json, then the theme index as int16 (-1 for
none). 52k papers is about 300 KB, drawn before the 4 MB of titles in
papers.json arrive.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

FORMAT_VERSION = 1
_QMAX = 65535


@dataclass(frozen=True)
class Theme:
    index: int
    name: str
    size: int
    cx: float
    cy: float
    top_category: str


def quantize(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[float]]:
    lo, hi = xy.min(0), xy.max(0)
    span = np.where(hi > lo, hi - lo, 1.0)
    q = np.rint((xy - lo) / span * _QMAX).astype("<u2")
    return q[:, 0], q[:, 1], [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])]


def write_map(
    out_dir: Path,
    *,
    ids: list[str],
    versions: list[str],
    titles: list[str],
    xy: np.ndarray,
    theme_index: np.ndarray,
    themes: list[Theme],
) -> None:
    n = len(ids)
    if not (len(versions) == len(titles) == len(xy) == len(theme_index) == n):
        raise ValueError("ids, versions, titles, xy and theme_index differ in length")
    qx, qy, bounds = quantize(xy)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "points.bin").open("wb") as f:
        f.write(qx.tobytes())
        f.write(qy.tobytes())
        f.write(theme_index.astype("<i2").tobytes())
    meta = {
        "version": FORMAT_VERSION,
        "generated": date.today().isoformat(),
        "from_month": min(i[:4] for i in ids),
        "to_month": max(i[:4] for i in ids),
        "n": n,
        "unthemed": int((theme_index < 0).sum()),
        "bounds": bounds,
        "themes": [
            {
                "name": t.name,
                "size": t.size,
                "cx": round(t.cx, 4),
                "cy": round(t.cy, 4),
                "top_category": t.top_category,
            }
            for t in sorted(themes, key=lambda t: t.index)
        ],
    }
    (out_dir / "map.json").write_text(json.dumps(meta, separators=(",", ":")))
    papers = {"ids": ids, "versions": versions, "titles": titles}
    (out_dir / "papers.json").write_text(json.dumps(papers, separators=(",", ":")))
