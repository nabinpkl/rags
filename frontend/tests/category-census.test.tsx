import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryCensus } from "@/components/landing/category-census";
import type { CategoryCensusResponse } from "@/lib/api-client";

const CENSUS: CategoryCensusResponse = {
  categories: ["cs.CV", "cs.LG"],
  months: [
    {
      month: "2607",
      papers: 13010,
      catalog_papers: 13016,
      categories: [
        { category: "cs.CV", papers: 2500 },
        { category: "cs.LG", papers: 2000 },
      ],
      other: 8510,
    },
    {
      month: "2608",
      papers: 14489,
      catalog_papers: 14491,
      categories: [
        { category: "cs.CV", papers: 2647 },
        { category: "cs.LG", papers: 2542 },
      ],
      other: 9300,
    },
  ],
  excluded: [{ month: "2609", papers_held: 408, catalog_papers: 5012 }],
};

describe("CategoryCensus", () => {
  it("states the share of each month, with the denominators under it", () => {
    render(<CategoryCensus census={CENSUS} />);

    expect(screen.getByText("19.2%")).toBeInTheDocument(); // 2500 of 13,010
    expect(screen.getByText("18.3%")).toBeInTheDocument(); // 2647 of 14,489
    expect(
      screen.getByText(/Jul 2026 13,010 of 13,016; Aug 2026 14,489 of 14,491/),
    ).toBeInTheDocument();
  });

  it("says why a month is absent instead of leaving a gap in the series", () => {
    // A month missing from a chart of the field's output reads as a month the
    // field went quiet, so the one we cannot draw is named with its share.
    render(<CategoryCensus census={CENSUS} />);

    expect(
      screen.getByText(/Left out: September 2026, where we hold 8% of the 5,012 papers/),
    ).toBeInTheDocument();
  });

  it("asks every month for the same categories, in the same order", () => {
    render(<CategoryCensus census={CENSUS} />);

    const rows = screen.getAllByRole("rowheader").map((cell) => cell.textContent);
    expect(rows).toEqual(["cs.CV", "cs.LG"]);
  });

  it("renders nothing when no month is held completely enough", () => {
    const { container } = render(
      <CategoryCensus census={{ categories: [], months: [], excluded: [] }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
