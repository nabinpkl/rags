import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CoverageStrip } from "@/components/catalog/coverage-strip";
import type { CoverageResponse } from "@/lib/api-client";

function month(
  id: string,
  held: number,
  catalog: number | null,
): CoverageResponse["months"][number] {
  return {
    month: id,
    papers_held: held,
    papers_parsed: held,
    refs_made: 0,
    catalog_papers: catalog,
  };
}

const MONTHS = [month("2606", 20, 12000), month("2607", 13010, 13016), month("2608", 6370, 14491)];

describe("CoverageStrip", () => {
  it("meters only the months the API names as the cohort", () => {
    render(<CoverageStrip coverage={{ months: MONTHS, cohort: ["2607", "2608"] }} />);

    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("44%")).toBeInTheDocument();
    // June 2026 is held thinly and is not the cohort: no meter for it.
    expect(screen.queryByText(/20 of 12,000/)).not.toBeInTheDocument();
  });

  it("keeps the exact counts behind each share", () => {
    render(<CoverageStrip coverage={{ months: MONTHS, cohort: ["2608"] }} />);

    expect(screen.getByTitle("August 2026: 6,370 of 14,491 papers")).toBeInTheDocument();
  });

  it("says n/a rather than 0% when the catalog cannot answer for a month", () => {
    render(<CoverageStrip coverage={{ months: [month("2608", 6370, null)], cohort: ["2608"] }} />);

    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("renders nothing with no cohort", () => {
    const { container } = render(<CoverageStrip coverage={{ months: MONTHS, cohort: [] }} />);

    expect(container).toBeEmptyDOMElement();
  });
});
