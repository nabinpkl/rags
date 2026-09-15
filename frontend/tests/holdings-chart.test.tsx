import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HoldingsChart } from "@/components/landing/holdings-chart";
import type { CoverageResponse } from "@/lib/api-client";

type Month = CoverageResponse["months"][number];

/** n id-months ending at 2609, thin everywhere except the last two.
 * Stepped through real calendar months: an id-month is YYMM, so plain
 * arithmetic on it invents "2596". */
function months(n: number): Month[] {
  return Array.from({ length: n }, (_, i) => {
    const date = new Date(Date.UTC(2026, 8 - (n - 1 - i), 1));
    const yy = String(date.getUTCFullYear()).slice(2);
    const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
    const month = `${yy}${mm}`;
    const dense = month >= "2608";
    return {
      month,
      papers_held: dense ? 7000 : 20,
      papers_parsed: dense ? 7000 : 0,
      refs_made: dense ? 60000 : 0,
      catalog_papers: 10000,
    };
  });
}

describe("HoldingsChart", () => {
  it("names the densest month with both numbers, so a bar cannot be read as arXiv's output", () => {
    render(<HoldingsChart months={months(14)} />);

    expect(screen.getByText(/Bar height is our collection, not arXiv/)).toBeInTheDocument();
    expect(screen.getByText(/we hold 7,000 of the 10,000 cs papers arXiv posted \(70%\)/)).toBeInTheDocument();
  });

  it("charts only the trailing 12 id-months", () => {
    render(<HoldingsChart months={months(14)} />);

    // 14 months ending 2609 => 2508..2609; the oldest two fall off.
    expect(screen.queryByTitle(/August 2025/)).not.toBeInTheDocument();
    expect(screen.getByTitle("October 2025: 20 papers we hold")).toBeInTheDocument();
  });

  it("states each row's own peak, since the two rows share no scale", () => {
    render(<HoldingsChart months={months(14)} />);

    expect(screen.getByText("peak 7,000")).toBeInTheDocument();
    expect(screen.getByText("peak 70%")).toBeInTheDocument();
  });

  it("draws no share bar for a month the catalog snapshot cannot answer for", () => {
    // Unknown is not zero: a 0% bar would assert we hold none of that month.
    const series = months(12);
    series[series.length - 1] = { ...series[series.length - 1], catalog_papers: null };
    const { container } = render(<HoldingsChart months={series} />);

    const unknown = container.querySelector(
      '[title$="no catalog total (the snapshot predates it)"] > div',
    );
    expect(unknown).toHaveStyle({ height: "0px" });
    // The papers row still shows the month: we do hold those papers.
    expect(screen.getByTitle("September 2026: 7,000 papers we hold")).toBeInTheDocument();
  });

  it("renders nothing with no months", () => {
    const { container } = render(<HoldingsChart months={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
