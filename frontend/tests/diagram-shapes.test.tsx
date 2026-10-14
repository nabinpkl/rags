import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Arrow, Box, Figure } from "@/components/architecture/diagram-shapes";

describe("diagram shapes", () => {
  it("colours every shape from theme tokens, never a literal", () => {
    const { container } = render(
      <Figure viewBox="0 0 100 100" label="x">
        <Box x={0} y={0} w={10} h={10} tone="amber" title="Gate" lines={["daily spend"]} />
        <Arrow id="a" d="M0 0 H10" color="teal" dashed />
      </Figure>,
    );
    for (const el of container.querySelectorAll("rect, path, text")) {
      expect(el.getAttribute("fill") ?? "none").toBe("none");
      expect(el.getAttribute("stroke")).toBeNull();
    }
  });

  it("points an arrow at the marker of its own colour", () => {
    const { container } = render(
      <svg>
        <Arrow id="a" d="M0 0 H10" color="teal" />
      </svg>,
    );
    expect(container.querySelector("path")?.getAttribute("marker-end")).toBe("url(#a-teal)");
  });
});
