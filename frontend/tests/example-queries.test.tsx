import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExampleQueries } from "@/components/benchmarks/example-queries";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

const EXAMPLES = BENCHMARK.examples;

describe("ExampleQueries", () => {
  it("badges each tab with hybrid's rank and the reranker's", () => {
    render(<ExampleQueries examples={EXAMPLES} k={10} />);
    expect(screen.getByLabelText("hybrid 8th, rerank 1st")).toBeInTheDocument();
    expect(screen.getByLabelText("hybrid 5th, rerank missed")).toBeInTheDocument();
  });

  it("shows hybrid's top 5 beside the reranked top 5", () => {
    render(<ExampleQueries examples={EXAMPLES} k={10} />);
    expect(screen.getByRole("heading", { name: "Hybrid" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reranked" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(10);
  });

  it("switches with a click and with the arrow keys", () => {
    render(<ExampleQueries examples={EXAMPLES} k={10} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[3]);
    expect(tabs[3]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs[3], { key: "ArrowRight" });
    expect(tabs[4]).toHaveAttribute("aria-selected", "true");
    expect(tabs[4]).toHaveFocus();
    fireEvent.keyDown(tabs[4], { key: "ArrowRight" });
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
  });

  it("prints a run of one paper's passages with the title once", () => {
    // Example 3's reranked list is five passages of one paper.
    render(<ExampleQueries examples={EXAMPLES} k={10} />);
    fireEvent.click(screen.getAllByRole("tab")[3]);
    const title = EXAMPLES[3].rerank[0].title;
    const lists = screen.getAllByRole("list").filter((l) => l.tagName === "OL");
    const reranked = lists[1];
    expect(reranked.textContent?.split(title).length).toBe(2);
  });
});
