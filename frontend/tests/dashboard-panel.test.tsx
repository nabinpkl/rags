import { render, screen } from "@testing-library/react";
import { ChartColumn } from "lucide-react";
import { describe, expect, it } from "vitest";

import { DashboardPanel } from "@/components/landing/dashboard-panel";

describe("DashboardPanel", () => {
  it("gives every region the same header shape: heading, meta, subtitle", () => {
    render(
      <DashboardPanel
        icon={ChartColumn}
        title="The corpus, month by month"
        meta="Sep ’25 – Sep ’26"
        description="Counted, not modelled."
        footer="Showing the top 3."
      >
        <p>body</p>
      </DashboardPanel>,
    );

    expect(screen.getByRole("heading", { name: "The corpus, month by month" })).toBeInTheDocument();
    expect(screen.getByText("Sep ’25 – Sep ’26")).toBeInTheDocument();
    expect(screen.getByText("Counted, not modelled.")).toBeInTheDocument();
    expect(screen.getByText("Showing the top 3.")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("omits the optional slots rather than reserving empty space for them", () => {
    const { container } = render(
      <DashboardPanel icon={ChartColumn} title="Bare">
        <p>body</p>
      </DashboardPanel>,
    );

    expect(container.querySelector("footer")).toBeNull();
    expect(container.querySelector("p")).toHaveTextContent("body");
  });
});
