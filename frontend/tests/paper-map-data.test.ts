import { afterEach, describe, expect, it, vi } from "vitest";

import {
  decodePoints,
  fetchMap,
  fetchPapers,
  type MapMeta,
  parseScope,
} from "@/lib/paper-map/paper-map-data";

const meta = (n: number): MapMeta => ({
  version: 1,
  digest: "abc123",
  generated: "2026-10-15",
  from_month: "2607",
  to_month: "2610",
  n,
  unthemed: 1,
  bounds: [-2, 10, 2, 14],
  themes: [],
  groups: [],
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

describe("fetching", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("revalidates map.json and fetches the other files by its digest", async () => {
    const m = meta(1);
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("map.json")) return new Response(JSON.stringify(m));
      if (url.includes("points.bin")) return new Response(encode([0], [0], [-1]));
      return new Response(JSON.stringify({ ids: [], versions: [], titles: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    await fetchMap("full");
    await fetchPapers("full", m.digest);
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      "/paper-map/full/map.json",
      "/paper-map/full/points.bin?v=abc123",
      "/paper-map/full/papers.json?v=abc123",
    ]);
    expect(fetchMock.mock.calls[0][1]).toEqual({ cache: "no-cache" });
  });
});

describe("parseScope", () => {
  it("opens on recent unless the URL asks for the full catalog", () => {
    expect(parseScope(null)).toBe("recent");
    expect(parseScope("full")).toBe("full");
    expect(parseScope("anything")).toBe("recent");
  });
});
