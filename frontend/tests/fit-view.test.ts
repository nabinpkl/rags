import { describe, expect, it } from "vitest";

import { fitView, project, themeBox } from "@/lib/paper-map/fit-view";

describe("fit-view", () => {
  it("centres the box and fits its longer side", () => {
    const v = fitView({ minX: 0, minY: 0, maxX: 10, maxY: 5 }, 1000, 1000, 1);
    expect(v.target).toEqual([5, 2.5, 0]);
    expect(2 ** v.zoom).toBeCloseTo(100);
  });

  it("projects with y up, centre to the middle of the viewport", () => {
    const v = { target: [5, 5, 0] as [number, number, number], zoom: 1 };
    expect(project(v, 200, 100, 5, 5)).toEqual([100, 50]);
    expect(project(v, 200, 100, 6, 6)).toEqual([102, 48]);
  });

  it("bounds only the members of a theme", () => {
    const xs = new Float32Array([0, 5, 9]);
    const ys = new Float32Array([1, 2, 8]);
    expect(themeBox(xs, ys, (i) => i < 2)).toEqual({ minX: 0, minY: 1, maxX: 5, maxY: 2 });
  });
});
