import { describe, expect, it } from "vitest";

import { cssRgb, lighten, parseColor, themeColors } from "@/lib/paper-map/theme-colors";

describe("theme colours", () => {
  it("gives every theme a distinct colour", () => {
    const c = themeColors(113).map(cssRgb);
    expect(new Set(c).size).toBe(113);
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
