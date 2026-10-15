import { describe, expect, it } from "vitest";

import { labelText, placeLabels, THEME_ZOOM, themeMinLevel } from "@/lib/paper-map/place-labels";

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
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 110, 102)], 0, 800, 600, "theme")).toEqual([
      1,
    ]);
  });

  it("places labels that do not touch", () => {
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 400, 300)], 0, 800, 600, "theme")).toEqual([
      1, 0,
    ]);
  });

  it("holds a label back until its zoom level", () => {
    expect(placeLabels([c(0, 10, 400, 300, 2)], 1, 800, 600, "theme")).toEqual([]);
    expect(placeLabels([c(0, 10, 400, 300, 2)], 2, 800, 600, "theme")).toEqual([0]);
  });

  it("brings themes in after the groups, the biggest first", () => {
    expect(themeMinLevel(0)).toBe(THEME_ZOOM);
    expect(themeMinLevel(12)).toBe(THEME_ZOOM + 1);
    expect(themeMinLevel(40)).toBe(THEME_ZOOM + 2);
  });

  it("skips labels that would be cut off at the viewport edge", () => {
    expect(placeLabels([c(0, 10, -500, 100)], 0, 800, 600, "theme")).toEqual([]);
    expect(placeLabels([c(0, 10, 10, 100)], 0, 800, 600, "theme")).toEqual([]);
    expect(placeLabels([c(0, 10, 400, 100)], 0, 800, 600, "theme")).toEqual([0]);
  });

  it("keeps a theme off a group label placed before it", () => {
    const taken: [number, number, number, number][] = [];
    expect(placeLabels([c(0, 10, 400, 300)], 0, 800, 600, "group", taken)).toEqual([0]);
    expect(placeLabels([c(0, 99, 405, 302)], 0, 800, 600, "theme", taken)).toEqual([]);
    expect(placeLabels([c(1, 5, 400, 100)], 0, 800, 600, "theme", taken)).toEqual([1]);
  });

  it("sets group names in capitals and leaves theme names as they are", () => {
    expect(labelText("robot · action · world", "group")).toBe("ROBOT · ACTION · WORLD");
    expect(labelText("robot · action · world", "theme")).toBe("robot · action · world");
  });
});
