/** Which labels to draw at a zoom. Group labels show at every zoom, set in
 * capitals and heavier; theme labels join from `THEME_ZOOM` on, smaller and
 * lighter, so the two levels read apart. Groups are placed first and themes
 * fill the space left. Biggest first, each label fully placed or skipped:
 * deck.gl's collision filter faded half-covered labels into ghosts. */

export type LabelKind = "group" | "theme";

export type LabelCandidate = {
  index: number;
  name: string;
  size: number;
  px: number;
  py: number;
  /** Zoom levels (log2 over the fitted view) from which it may show. */
  minLevel: number;
};

export type Box = [number, number, number, number];

/** Zoom levels from which theme labels join the group labels. */
export const THEME_ZOOM = 1;

export const LABEL_STYLE = {
  group: { px: 16, weight: 800, charWidth: 0.68 },
  theme: { px: 14, weight: 500, charWidth: 0.55 },
} as const;

export function labelText(name: string, kind: LabelKind): string {
  return kind === "group" ? name.toUpperCase() : name;
}

/** Themes ranked by size: the first 12 from THEME_ZOOM, the next 28 a level
 * further, the rest two levels further. */
export function themeMinLevel(rank: number): number {
  return THEME_ZOOM + (rank < 12 ? 0 : rank < 40 ? 1 : 2);
}

/** Indices of the candidates placed, biggest first. `taken` holds boxes
 * already placed (by an earlier call) and gains this call's boxes. */
export function placeLabels(
  candidates: LabelCandidate[],
  zoomLevels: number,
  width: number,
  height: number,
  kind: LabelKind,
  taken: Box[] = [],
): number[] {
  const { px, charWidth } = LABEL_STYLE[kind];
  const ranked = candidates.filter((c) => c.minLevel <= zoomLevels).sort((a, b) => b.size - a.size);
  const out: number[] = [];
  for (const c of ranked) {
    const w = c.name.length * px * charWidth;
    const h = px * 1.4;
    const box: Box = [c.px - w / 2, c.py - h / 2, c.px + w / 2, c.py + h / 2];
    if (box[0] < 0 || box[2] > width || box[1] < 0 || box[3] > height) continue;
    if (taken.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]))
      continue;
    taken.push(box);
    out.push(c.index);
  }
  return out;
}
