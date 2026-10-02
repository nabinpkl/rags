import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardPanel } from "@/components/landing/dashboard-panel";

describe("DashboardPanel", () => {
  it("gives every region the same header shape: heading, meta, subtitle", () => {
    render(
      <DashboardPanel
        title="Most cited"
        meta="Jul – Sep 2026"
        description="Counted, not modelled."
        footer="Left out: September."
      >
        <p>body</p>
      </DashboardPanel>,
    );

    expect(screen.getByRole("heading", { name: "Most cited" })).toBeInTheDocument();
    expect(screen.getByText("Jul – Sep 2026")).toBeInTheDocument();
    expect(screen.getByText("Counted, not modelled.")).toBeInTheDocument();
    expect(screen.getByText("Left out: September.")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("omits the optional slots rather than reserving empty space for them", () => {
    const { container } = render(
      <DashboardPanel title="Bare">
        <p>body</p>
      </DashboardPanel>,
    );

    expect(container.querySelector("footer")).toBeNull();
    expect(container.querySelector("p")).toHaveTextContent("body");
  });
});
