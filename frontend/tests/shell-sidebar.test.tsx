import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VIEWS, ShellSidebar } from "@/components/shell/shell-sidebar";

describe("ShellSidebar", () => {
  it("offers every view as a link, from any view", () => {
    render(<ShellSidebar current="citations" />);

    const nav = screen.getByRole("navigation", { name: "Views" });
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(VIEWS.map((view) => view.label));
    expect(nav).toContainElement(links[0] ?? null);
    expect(screen.getByRole("link", { name: "Explore" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Citations" })).toHaveAttribute("href", "/citations");
    expect(screen.getByRole("link", { name: "Trends" })).toHaveAttribute("href", "/trends");
    expect(screen.getByRole("link", { name: "RAG Demo" })).toHaveAttribute("href", "/demo");
  });

  it("leads with Explore, the home page", () => {
    render(<ShellSidebar current="demo" />);

    const labels = screen.getAllByRole("link").map((link) => link.textContent);
    expect(labels).toEqual(["Explore", "Citations", "Trends", "RAG Demo", "Benchmarks"]);
    expect(screen.getByRole("link", { name: "RAG Demo" })).toHaveAttribute("aria-current", "page");
  });

  it("marks the view being read, and only that one", () => {
    render(<ShellSidebar current="explore" />);

    expect(screen.getByRole("link", { name: "Explore" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Citations" })).not.toHaveAttribute("aria-current");
  });

  it("mounts a view's own controls under the nav rather than beside it", () => {
    render(
      <ShellSidebar current="explore">
        <button type="button">Clear the filter</button>
      </ShellSidebar>,
    );

    expect(screen.getByRole("button", { name: "Clear the filter" })).toBeInTheDocument();
  });
});
