import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardSidebar, SECTIONS } from "@/components/landing/dashboard-sidebar";

describe("DashboardSidebar", () => {
  it("lists every band of the canvas, in canvas order", () => {
    render(
      <DashboardSidebar active={null} windowLabel="Nov 2007 – Sep 2026" onNavigate={vi.fn()} />,
    );

    const rows = screen.getAllByRole("button");
    expect(rows.map((row) => row.textContent)).toEqual(SECTIONS.map((section) => section.label));
  });

  it("marks the band being read, and only that one", () => {
    render(<DashboardSidebar active="activity" windowLabel={null} onNavigate={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Activity" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("hands the band id back rather than navigating itself — the canvas may not be mounted", () => {
    const onNavigate = vi.fn();
    render(<DashboardSidebar active="overview" windowLabel={null} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole("button", { name: "Foundations" }));

    expect(onNavigate).toHaveBeenCalledWith("foundations");
  });

  it("says the window is not yet counted rather than printing an empty range", () => {
    render(<DashboardSidebar active={null} windowLabel={null} onNavigate={vi.fn()} />);

    expect(screen.getByText("not yet counted")).toBeInTheDocument();
  });
});
