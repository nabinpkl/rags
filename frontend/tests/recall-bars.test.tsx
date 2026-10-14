import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecallBars } from "@/components/architecture/recall-bars";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

describe("RecallBars", () => {
  it("shows the four retrieval steps with recall from the benchmark export", () => {
    render(<RecallBars board={BENCHMARK.board} k={BENCHMARK.k} n={BENCHMARK.n} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    const rerank = BENCHMARK.board.find((b) => b.config === "rerank");
    expect(items[3]).toHaveTextContent(`${Math.round((rerank?.recall ?? 0) * 100)}%`);
  });

  it("marks only fusion plus rerank as what live search runs", () => {
    render(<RecallBars board={BENCHMARK.board} k={BENCHMARK.k} n={BENCHMARK.n} />);
    expect(screen.getAllByText("live")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")[3]).toHaveTextContent("live");
  });

  it("fails loud when the export lacks a step", () => {
    const board = BENCHMARK.board.filter((b) => b.config !== "rerank");
    expect(() => render(<RecallBars board={board} k={10} n={1} />)).toThrow(/no rerank row/);
  });
});
