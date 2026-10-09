import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardShell } from "@/components/shell/dashboard-shell";

// Docked (desktop): the rail is in the page rather than behind the drawer.
beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    matches: true,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DashboardShell", () => {
  it("frames a view: rail with it marked current, its breadcrumb, its canvas", () => {
    render(
      <DashboardShell current="trends" trail={<li>Trends</li>}>
        <p>canvas body</p>
      </DashboardShell>,
    );

    expect(screen.getByRole("link", { name: "Trends" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Trends");
    expect(screen.getByRole("main")).toHaveTextContent("canvas body");
  });

  it("keeps the arXiv attribution footer on every dashboard view", () => {
    render(
      <DashboardShell current="citations" trail={<li>Citations</li>}>
        <p>body</p>
      </DashboardShell>,
    );

    expect(screen.getByText(/Thank you to arXiv/)).toBeInTheDocument();
  });
});
