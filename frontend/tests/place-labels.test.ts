import { describe, expect, it } from "vitest";

import { placeLabels, THEME_ZOOM, themeMinLevel } from "@/lib/paper-map/place-labels";

const c = (
  index: number,
  size: number,
  px: number,
  py: number,
  minLevel = 0,
  name = "theme name",
) => ({
  index,
  name,
  size,
  px,
  py,
  minLevel,
});

describe("placeLabels", () => {
  it("keeps the bigger label when two would overlap", () => {
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 110, 102)], 0, 800, 600, 14)).toEqual([1]);
  });

  it("places labels that do not touch", () => {
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 400, 300)], 0, 800, 600, 14)).toEqual([1, 0]);
  });

  it("holds a label back until its zoom level", () => {
    expect(placeLabels([c(0, 10, 400, 300, 2)], 1, 800, 600, 14)).toEqual([]);
    expect(placeLabels([c(0, 10, 400, 300, 2)], 2, 800, 600, 14)).toEqual([0]);
  });

  it("brings themes in after the groups, the biggest first", () => {
    expect(themeMinLevel(0)).toBe(THEME_ZOOM);
    expect(themeMinLevel(12)).toBe(THEME_ZOOM + 1);
    expect(themeMinLevel(40)).toBe(THEME_ZOOM + 2);
  });

  it("skips labels that would be cut off at the viewport edge", () => {
    expect(placeLabels([c(0, 10, -500, 100)], 0, 800, 600, 14)).toEqual([]);
    expect(placeLabels([c(0, 10, 10, 100)], 0, 800, 600, 14)).toEqual([]);
    expect(placeLabels([c(0, 10, 400, 100)], 0, 800, 600, 14)).toEqual([0]);
  });
});
