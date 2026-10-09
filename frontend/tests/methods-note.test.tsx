import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MethodsNote } from "@/components/landing/methods-note";
import type { LandingResponse } from "@/lib/api-client";

const STATS: LandingResponse["stats"] = {
  cohort_start: "2607",
  cohort_end: "2608",
  cohort_papers: 19380,
  cohort_catalog_papers: 27507,
  readable_papers: 667,
  papers_parsed: 18844,
  papers_with_references: 15905,
  citations: 162792,
  cited_works: 63457,
};

describe("MethodsNote", () => {
  it("starts folded, one click from the method", () => {
    const { container } = render(<MethodsNote stats={STATS} />);

    expect(container.querySelector("details")).not.toHaveAttribute("open");
    expect(screen.getByText("How this is counted")).toBeInTheDocument();
  });

  it("states the parse rate over the papers that reached the parser", () => {
    // Counted over every catalog row it printed 30% for a parser that yields 84%.
    render(<MethodsNote stats={STATS} />);

    expect(screen.getByText(/84% of papers yield one/)).toBeInTheDocument();
  });

  it("keeps the clustering-stability finding, the reason there are no themes", () => {
    render(<MethodsNote stats={STATS} />);

    expect(screen.getByText(/agree on only 43–61% of pairs/)).toBeInTheDocument();
  });

  it("survives an empty graph without dividing by zero", () => {
    render(<MethodsNote stats={{ ...STATS, papers_parsed: 0, papers_with_references: 0 }} />);

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
