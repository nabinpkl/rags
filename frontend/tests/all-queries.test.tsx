import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AllQueries } from "@/components/benchmarks/all-queries";
import type { QueryRanks } from "@/lib/benchmarks/retrieval-benchmark";

const rank = (r: (number | null)[]) => ({ rerank: r, hybrid: r, bm25: r, vector: r, rewrite: r });
const QUERIES: QueryRanks[] = [
  {
    question: "how many basis functions give stable kernel fits",
    type: "single_hop",
    rank: rank([1]),
  },
  { question: "which two parts agree", type: "multi_hop", rank: rank([null, 4]) },
];

describe("AllQueries", () => {
  it("draws one chip per expected passage, a dash for a miss", () => {
    render(<AllQueries queries={QUERIES} k={10} />);
    expect(screen.getAllByTitle("not in top 10").length).toBeGreaterThanOrEqual(5);
    expect(screen.getAllByTitle("4th")).toHaveLength(5);
  });

  it("filters by question type", () => {
    render(<AllQueries queries={QUERIES} k={10} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "multi_hop" } });
    expect(screen.getByText("1 queries")).toBeInTheDocument();
    expect(screen.queryByText(QUERIES[0].question)).not.toBeInTheDocument();
  });
});
