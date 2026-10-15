import { describe, expect, it } from "vitest";

import { labelTier, placeLabels } from "@/lib/paper-map/place-labels";

const c = (index: number, size: number, px: number, py: number, name = "theme name") => ({
  index,
  name,
  size,
  px,
  py,
});

describe("placeLabels", () => {
  it("keeps the bigger theme when two labels would overlap", () => {
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 110, 102)], 0, 800, 600)).toEqual([1]);
  });

  it("places labels that do not touch", () => {
    expect(placeLabels([c(0, 10, 100, 100), c(1, 50, 400, 300)], 0, 800, 600)).toEqual([1, 0]);
  });

  it("holds smaller themes back until zoomed in", () => {
    const many = Array.from({ length: 13 }, (_, i) => c(i, 100 - i, 60 * i, 40 * i, "x"));
    expect(placeLabels(many, 0, 2000, 2000)).not.toContain(12);
    expect(placeLabels(many, 1, 2000, 2000)).toContain(12);
    expect(labelTier(11)).toBe(0);
    expect(labelTier(39)).toBe(1);
    expect(labelTier(40)).toBe(2);
  });

  it("skips labels outside the viewport", () => {
    expect(placeLabels([c(0, 10, -500, 100)], 0, 800, 600)).toEqual([]);
  });
});
