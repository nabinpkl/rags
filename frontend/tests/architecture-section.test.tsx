import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArchitectureSection } from "@/components/architecture/architecture-section";

describe("ArchitectureSection", () => {
  it("is a region named by its heading", () => {
    render(
      <ArchitectureSection id="agent" title="Agent" subtitle="The loop.">
        <p>figure</p>
      </ArchitectureSection>,
    );
    expect(screen.getByRole("region", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByText("The loop.")).toBeInTheDocument();
  });
});
