/** deck.gl OrthographicView state that fits a box in a viewport. Zoom is
 * log2 of pixels per data unit. */

export type Box = { minX: number; minY: number; maxX: number; maxY: number };
export type MapViewState = { target: [number, number, number]; zoom: number };

export function fitView(box: Box, width: number, height: number, pad = 0.9): MapViewState {
  const w = Math.max(box.maxX - box.minX, 1e-6);
  const h = Math.max(box.maxY - box.minY, 1e-6);
  return {
    target: [(box.minX + box.maxX) / 2, (box.minY + box.maxY) / 2, 0],
    zoom: Math.log2(Math.min(width / w, height / h) * pad),
  };
}

/** Screen position of a data point under a view (y up, as flipY: false). */
export function project(
  view: MapViewState,
  width: number,
  height: number,
  x: number,
  y: number,
): [number, number] {
  const s = 2 ** view.zoom;
  return [(x - view.target[0]) * s + width / 2, height / 2 - (y - view.target[1]) * s];
}

export function themeBox(xs: Float32Array, ys: Float32Array, members: (i: number) => boolean): Box {
  const box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (let i = 0; i < xs.length; i++) {
    if (!members(i)) continue;
    box.minX = Math.min(box.minX, xs[i]);
    box.maxX = Math.max(box.maxX, xs[i]);
    box.minY = Math.min(box.minY, ys[i]);
    box.maxY = Math.max(box.maxY, ys[i]);
  }
  return box;
}
