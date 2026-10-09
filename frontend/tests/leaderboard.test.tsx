import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Leaderboard } from "@/components/benchmarks/leaderboard";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

function board() {
  render(<Leaderboard board={BENCHMARK.board} k={10} poolK={50} hardware={BENCHMARK.hardware} />);
  return screen.getAllByRole("row").slice(1);
}

describe("Leaderboard", () => {
  it("ranks the methods by recall, best first", () => {
    const names = board().map((r) => within(r).getByRole("rowheader").textContent);
    expect(names[0]).toMatch(/^Hybrid \+ rerank/);
    expect(names).toHaveLength(BENCHMARK.board.length);
  });

  it("keeps MRR beside nDCG", () => {
    board();
    expect(screen.getByText("MRR")).toBeInTheDocument();
    expect(screen.getByText("nDCG@10")).toBeInTheDocument();
  });

  it("names the hardware behind the latency, never 'this CPU'", () => {
    board();
    expect(screen.getByText("Latency")).toHaveAttribute(
      "title",
      expect.stringContaining("4-core Arm server (Neoverse N1)"),
    );
  });

  it("says why the pinned row has no interval", () => {
    board();
    expect(screen.getByRole("img", { name: /no interval: run 492b61d7e3a5/ })).toBeInTheDocument();
  });
});
