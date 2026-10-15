"""Write the map the /map page reads: points.bin, map.json, papers.json.

points.bin is three little-endian arrays back to back, each n long: x and y
as uint16 over the bounds in map.json, then the theme index as int16 (-1 for
none). 52k papers is about 300 KB, drawn before the 4 MB of titles in
papers.json arrive.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

FORMAT_VERSION = 2
_QMAX = 65535


@dataclass(frozen=True)
class Theme:
    index: int
    name: str
    size: int
    cx: float
    cy: float
    top_category: str
    group: int


@dataclass(frozen=True)
class Group:
    index: int
    name: str
    size: int
    cx: float
    cy: float


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
    groups: list[Group],
) -> None:
    n = len(ids)
    if not (len(versions) == len(titles) == len(xy) == len(theme_index) == n):
        raise ValueError("ids, versions, titles, xy and theme_index differ in length")
    qx, qy, bounds = quantize(xy)
    points = qx.tobytes() + qy.tobytes() + theme_index.astype("<i2").tobytes()
    papers = json.dumps(
        {"ids": ids, "versions": versions, "titles": titles}, separators=(",", ":")
    ).encode()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "points.bin").write_bytes(points)
    (out_dir / "papers.json").write_bytes(papers)
    meta = {
        "version": FORMAT_VERSION,
        # The page fetches the other two files with ?v=<digest>, so a rebuild
        # changes their URLs and no cache can pair new meta with old points.
        "digest": hashlib.sha256(points + papers).hexdigest()[:16],
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
                "group": t.group,
            }
            for t in sorted(themes, key=lambda t: t.index)
        ],
        "groups": [
            {"name": g.name, "size": g.size, "cx": round(g.cx, 4), "cy": round(g.cy, 4)}
            for g in sorted(groups, key=lambda g: g.index)
        ],
    }
    (out_dir / "map.json").write_text(json.dumps(meta, separators=(",", ":")))
