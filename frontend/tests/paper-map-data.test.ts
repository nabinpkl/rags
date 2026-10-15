import { describe, expect, it } from "vitest";

import { decodePoints, type MapMeta } from "@/lib/paper-map/paper-map-data";

const meta = (n: number): MapMeta => ({
  version: 1,
  generated: "2026-10-15",
  from_month: "2607",
  to_month: "2610",
  n,
  unthemed: 1,
  bounds: [-2, 10, 2, 14],
  themes: [],
});

function encode(xs: number[], ys: number[], themes: number[]): ArrayBuffer {
  const n = xs.length;
  const buf = new ArrayBuffer(n * 6);
  const v = new DataView(buf);
  xs.forEach((x, i) => v.setUint16(2 * i, x, true));
  ys.forEach((y, i) => v.setUint16(2 * n + 2 * i, y, true));
  themes.forEach((t, i) => v.setInt16(4 * n + 2 * i, t, true));
  return buf;
}

describe("decodePoints", () => {
  it("maps uint16 back onto the bounds and keeps -1 as no theme", () => {
    const p = decodePoints(encode([0, 65535], [65535, 0], [3, -1]), meta(2));
    expect(Array.from(p.x)).toEqual([-2, 2]);
    expect(Array.from(p.y)).toEqual([14, 10]);
    expect(Array.from(p.theme)).toEqual([3, -1]);
  });

  it("rejects a file whose size does not match the paper count", () => {
    expect(() => decodePoints(new ArrayBuffer(10), meta(2))).toThrow(/2 papers need 12/);
  });
});
