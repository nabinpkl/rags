/** Which theme labels to draw at a zoom: biggest theme first, each label
 * either fully placed or skipped. All-or-nothing on purpose: deck.gl's
 * collision filter samples a low-resolution map and fades half-covered
 * labels, which read as ghosts. */

export type LabelCandidate = { index: number; name: string; size: number; px: number; py: number };

/** Themes ranked by size: the first 12 always, the next 28 from 2x zoom,
 * the rest from 4x. `zoomLevels` is log2 of zoom over the fitted view. */
export function labelTier(rank: number): number {
  return rank < 12 ? 0 : rank < 40 ? 1 : 2;
}

export const LABEL_PX = { tier0: 16, rest: 14 } as const;

export function placeLabels(
  candidates: LabelCandidate[],
  zoomLevels: number,
  width: number,
  height: number,
): number[] {
  const ranked = [...candidates].sort((a, b) => b.size - a.size);
  const placed: [number, number, number, number][] = [];
  const out: number[] = [];
  ranked.forEach((c, rank) => {
    const tier = labelTier(rank);
    if (tier > zoomLevels) return;
    const px = tier === 0 ? LABEL_PX.tier0 : LABEL_PX.rest;
    const w = c.name.length * px * 0.55;
    const h = px * 1.4;
    const box: [number, number, number, number] = [
      c.px - w / 2,
      c.py - h / 2,
      c.px + w / 2,
      c.py + h / 2,
    ];
    if (box[0] < 0 || box[2] > width || box[1] < 0 || box[3] > height) return;
    if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]))
      return;
    placed.push(box);
    out.push(c.index);
  });
  return out;
}
