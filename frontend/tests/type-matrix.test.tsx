import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TypeMatrix } from "@/components/benchmarks/type-matrix";
import type { TypeRecall } from "@/lib/benchmarks/retrieval-benchmark";

const BY_TYPE: TypeRecall[] = [
  { type: "single_hop", n: 26, recall: { rerank: 1, hybrid: 0.996, bm25: 0.96 } },
  { type: "multi_hop", n: 10, recall: { rerank: 0.7, hybrid: 0.55, bm25: 0.45 } },
];

describe("TypeMatrix", () => {
  it("labels types in the reader's words with their counts", () => {
    render(<TypeMatrix byType={BY_TYPE} configs={["rerank", "hybrid", "bm25"]} k={10} />);
    expect(screen.getByText("Plain lookup")).toBeInTheDocument();
    expect(screen.getByText("Two passages")).toBeInTheDocument();
    expect(screen.getByText("26")).toBeInTheDocument();
  });

  it("bolds every value that prints as the column's best", () => {
    render(<TypeMatrix byType={BY_TYPE} configs={["rerank", "hybrid", "bm25"]} k={10} />);
    // 1.00 and 0.996 both print 100%.
    const cells = screen.getAllByText("100%");
    expect(cells).toHaveLength(2);
    for (const c of cells) expect(c).toHaveClass("font-bold");
    expect(screen.getByText("55%")).not.toHaveClass("font-bold");
  });
});
