/** Which labels to draw at a zoom. Zoomed out the map names its umbrella
 * groups; from `THEME_ZOOM` on it names the specific themes, more of them
 * the further in. Biggest first, each label fully placed or skipped:
 * deck.gl's collision filter faded half-covered labels into ghosts. */

export type LabelCandidate = {
  index: number;
  name: string;
  size: number;
  px: number;
  py: number;
  /** Zoom levels (log2 over the fitted view) from which it may show. */
  minLevel: number;
};

/** Zoom levels from which theme labels replace group labels. */
export const THEME_ZOOM = 1;

export const LABEL_PX = { group: 16, theme: 14 } as const;

/** Themes ranked by size: the first 12 from THEME_ZOOM, the next 28 a level
 * further, the rest two levels further. */
export function themeMinLevel(rank: number): number {
  return THEME_ZOOM + (rank < 12 ? 0 : rank < 40 ? 1 : 2);
}

export function placeLabels(
  candidates: LabelCandidate[],
  zoomLevels: number,
  width: number,
  height: number,
  px: number,
): number[] {
  const ranked = candidates.filter((c) => c.minLevel <= zoomLevels).sort((a, b) => b.size - a.size);
  const placed: [number, number, number, number][] = [];
  const out: number[] = [];
  for (const c of ranked) {
    const w = c.name.length * px * 0.55;
    const h = px * 1.4;
    const box: [number, number, number, number] = [
      c.px - w / 2,
      c.py - h / 2,
      c.px + w / 2,
      c.py + h / 2,
    ];
    if (box[0] < 0 || box[2] > width || box[1] < 0 || box[3] > height) continue;
    if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]))
      continue;
    placed.push(box);
    out.push(c.index);
  }
  return out;
}
