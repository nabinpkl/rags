import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VIEWS, ShellSidebar } from "@/components/shell/shell-sidebar";

describe("ShellSidebar", () => {
  it("offers both views as links, from either view", () => {
    render(<ShellSidebar current="overview" />);

    const nav = screen.getByRole("navigation", { name: "Views" });
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(VIEWS.map((view) => view.label));
    expect(nav).toContainElement(links[0] ?? null);
    expect(screen.getByRole("link", { name: "Explore" })).toHaveAttribute("href", "/papers");
  });

  it("marks the view being read, and only that one", () => {
    render(<ShellSidebar current="explore" />);

    expect(screen.getByRole("link", { name: "Explore" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("mounts a view's own controls under the nav rather than beside it", () => {
    render(
      <ShellSidebar current="explore">
        <button type="button">Clear the filter</button>
      </ShellSidebar>,
    );

    expect(screen.getByRole("button", { name: "Clear the filter" })).toBeInTheDocument();
  });

  it("says the cohort is not yet counted rather than printing an empty range", () => {
    render(<ShellSidebar current="overview" cohort={null} />);

    expect(screen.getByText("not yet counted")).toBeInTheDocument();
  });

  it("leaves the cohort out entirely where nothing on screen was counted over it", () => {
    render(<ShellSidebar current="explore" />);

    expect(screen.queryByText("Cohort")).not.toBeInTheDocument();
  });
});
