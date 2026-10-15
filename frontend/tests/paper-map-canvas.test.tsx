import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const deck = vi.hoisted(() => ({ setProps: vi.fn(), finalize: vi.fn(), ctor: vi.fn() }));

vi.mock("@deck.gl/core", () => ({
  Deck: class {
    constructor(props: unknown) {
      deck.ctor(props);
    }
    setProps = deck.setProps;
    finalize = deck.finalize;
  },
  OrthographicView: class {},
  LinearInterpolator: class {},
}));
vi.mock("@deck.gl/layers", () => ({
  ScatterplotLayer: class {
    constructor(public props: { id: string; data: unknown }) {}
  },
  TextLayer: class {
    constructor(public props: { id: string; data: { name: string }[] }) {}
  },
}));

import { PaperMapCanvas } from "@/components/paper-map/paper-map-canvas";

const meta = {
  version: 1,
  generated: "2026-10-15",
  from_month: "2607",
  to_month: "2610",
  n: 2,
  unthemed: 1,
  bounds: [0, 0, 10, 10] as [number, number, number, number],
  themes: [{ name: "robot · arm", size: 1, cx: 5, cy: 5, top_category: "cs.RO" }],
};
const points = {
  n: 2,
  x: new Float32Array([5, 1]),
  y: new Float32Array([5, 1]),
  theme: new Int16Array([0, -1]),
};

describe("PaperMapCanvas", () => {
  it("draws the papers and the theme label, and finalizes the deck on unmount", () => {
    document.documentElement.style.setProperty("--ink", "#1a2128");
    document.documentElement.style.setProperty("--paper", "#e6e8e3");
    const { unmount } = render(
      <PaperMapCanvas
        meta={meta}
        points={points}
        colors={[[200, 50, 50]]}
        hideUnthemed={false}
        brightness={0}
        selectedTheme={null}
        colorScheme="light"
        onHover={() => {}}
        onPick={() => {}}
      />,
    );
    expect(deck.ctor).toHaveBeenCalledWith(expect.objectContaining({ pickingRadius: 6 }));
    const layers = deck.setProps.mock.calls.at(-1)?.[0].layers;
    expect(layers.map((l: { props: { id: string } }) => l.props.id)).toEqual(["papers", "labels"]);
    expect(layers[1].props.data.map((t: { name: string }) => t.name)).toEqual(["robot · arm"]);
    unmount();
    expect(deck.finalize).toHaveBeenCalled();
  });
});
