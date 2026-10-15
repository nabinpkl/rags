import { describe, expect, it } from "vitest";

import {
  cssRgb,
  groupColors,
  lighten,
  parseColor,
  themeColors,
} from "@/lib/paper-map/theme-colors";

describe("theme colours", () => {
  it("gives every group a distinct colour", () => {
    expect(new Set(groupColors(20).map(cssRgb)).size).toBe(20);
  });

  it("shades themes within a group apart from each other", () => {
    const c = themeColors([0, 0, 0, 1]).map(cssRgb);
    expect(new Set(c.slice(0, 3)).size).toBe(3);
  });

  it("lightens toward white by at most 60%", () => {
    expect(lighten([0, 100, 255], 0)).toEqual([0, 100, 255]);
    expect(lighten([0, 100, 255], 1)).toEqual([153, 193, 255]);
  });

  it("parses the page's hex and rgb tokens and refuses anything else", () => {
    expect(parseColor(" #1a2128 ")).toEqual([26, 33, 40]);
    expect(parseColor("rgb(8, 12, 18)")).toEqual([8, 12, 18]);
    expect(() => parseColor("oklch(0.5 0.1 200)")).toThrow(/unparseable/);
  });
});
