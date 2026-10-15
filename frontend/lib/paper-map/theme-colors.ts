/** Colours: one hue per umbrella group (golden-angle, so neighbours in size
 * order differ), and each theme a shade of its group's hue, so a group reads
 * as one region zoomed out and its themes stay apart zoomed in. RGB tuples
 * because deck.gl takes numbers, not CSS. */

export type RGB = [number, number, number];

export const UNTHEMED_RGB: RGB = [150, 150, 158];

const hue = (group: number) => (group * 137.508) % 360;

export function groupColors(count: number): RGB[] {
  return Array.from({ length: count }, (_, g) => hslToRgb(hue(g), 0.6, 0.52));
}

/** `groupOf[i]` is theme i's group. Shades step through lightness and
 * saturation in the order themes appear within their group. */
export function themeColors(groupOf: number[]): RGB[] {
  const seen = new Map<number, number>();
  return groupOf.map((g) => {
    const k = seen.get(g) ?? 0;
    seen.set(g, k + 1);
    const l = [0.5, 0.62, 0.42, 0.7, 0.56, 0.36][k % 6];
    const s = [0.62, 0.5, 0.7, 0.45][k % 4];
    return hslToRgb((hue(g) + ((k % 3) - 1) * 8 + 360) % 360, s, l);
  });
}

/** Mix toward white by `k` in [0, 1] (at most 60%), for dark backgrounds. */
export function lighten([r, g, b]: RGB, k: number): RGB {
  const f = (v: number) => Math.round(v + (255 - v) * k * 0.6);
  return [f(r), f(g), f(b)];
}

export function cssRgb([r, g, b]: RGB): string {
  return `rgb(${r} ${g} ${b})`;
}

/** "#1a2128" or "rgb(26 33 40)" to a tuple; the page's tokens are hex. */
export function parseColor(value: string): RGB {
  const v = value.trim();
  const hex = /^#([0-9a-f]{6})$/i.exec(v);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(v);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  throw new Error(`unparseable colour: ${value}`);
}

function hslToRgb(h: number, s: number, l: number): RGB {
  const a = s * Math.min(l, 1 - l);
  const f = (k: number) => {
    const m = (k + h / 30) % 12;
    return Math.round(255 * (l - a * Math.max(-1, Math.min(m - 3, 9 - m, 1))));
  };
  return [f(0), f(8), f(4)];
}
