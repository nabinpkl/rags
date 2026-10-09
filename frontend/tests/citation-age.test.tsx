import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CitationAge } from "@/components/landing/citation-age";
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

const CITED_YEARS: LandingResponse["cited_years"] = [
  { year: 2018, citations: 10 },
  { year: 2020, citations: 10 },
  { year: 2024, citations: 40 },
  { year: 2026, citations: 30 },
  { year: null, citations: 10 },
];

describe("CitationAge", () => {
  it("measures reach against the cohort's own year, counting undated work as older", () => {
    // Cohort ends 2608, so the year is 2026: everything but the 2026 bucket
    // (30 of 100) predates it.
    render(<CitationAge stats={STATS} citedYears={CITED_YEARS} />);

    expect(
      screen.getByText("70% of citations point at work from before 2026."),
    ).toBeInTheDocument();
  });

  it("draws bars only from 2020 on", () => {
    render(<CitationAge stats={STATS} citedYears={CITED_YEARS} />);

    expect(screen.getByText("2020")).toBeInTheDocument();
    expect(screen.queryByText("2018")).not.toBeInTheDocument();
  });

  it("says so plainly when there is nothing to place in time", () => {
    render(<CitationAge stats={STATS} citedYears={[]} />);

    expect(screen.getByText("No citations to place in time yet.")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
