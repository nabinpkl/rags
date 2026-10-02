import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Hero } from "@/components/landing/hero";
import type { CoverageResponse, LandingResponse } from "@/lib/api-client";

function stats(overrides: Partial<LandingResponse["stats"]> = {}): LandingResponse["stats"] {
  return {
    cohort_start: "2607",
    cohort_end: "2608",
    cohort_papers: 19380,
    cohort_catalog_papers: 27507,
    readable_papers: 667,
    papers_parsed: 20733,
    papers_with_references: 16893,
    citations: 172404,
    cited_works: 65694,
    ...overrides,
  };
}

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

describe("Hero", () => {
  it("prints no corpus totals: they size our pile, not the finding", () => {
    render(<Hero stats={stats()} months={MONTHS} />);

    expect(screen.queryByText(/172,404/)).not.toBeInTheDocument();
    expect(screen.queryByText(/65,694/)).not.toBeInTheDocument();
    expect(screen.queryByText(/667/)).not.toBeInTheDocument();
  });

  it("meters only the cohort's months, each against arXiv's own count", () => {
    render(<Hero stats={stats()} months={MONTHS} />);

    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("44%")).toBeInTheDocument();
    expect(screen.getByText(/6,370 of 14,491 papers/)).toBeInTheDocument();
    // June 2026 is outside the cohort and is not drawn.
    expect(screen.queryByText(/20 of 12,000/)).not.toBeInTheDocument();
  });

  it("says n/a rather than 0% when the catalog cannot answer for a month", () => {
    render(<Hero stats={stats()} months={[month("2608", 6370, null)]} />);

    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("names the cohort from the id-months the API derived, each with its own year", () => {
    render(<Hero stats={stats({ cohort_start: "2512", cohort_end: "2609" })} />);

    expect(screen.getByText(/from December 2025 to September 2026/)).toBeInTheDocument();
  });

  it("says one month when the cohort is one month", () => {
    render(<Hero stats={stats({ cohort_start: "2608", cohort_end: "2608" })} />);

    expect(screen.getByText(/posted in August 2026/)).toBeInTheDocument();
  });

  it("degrades to a neutral phrase and no meters on an empty graph", () => {
    const { container } = render(
      <Hero stats={stats({ cohort_start: null, cohort_end: null })} months={MONTHS} />,
    );

    expect(screen.getByText(/in the indexed months/)).toBeInTheDocument();
    expect(container.querySelector("dl")).toBeNull();
  });
});
