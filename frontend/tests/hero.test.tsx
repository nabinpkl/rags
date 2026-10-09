import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Hero } from "@/components/landing/hero";
import type { LandingResponse } from "@/lib/api-client";

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

describe("Hero", () => {
  it("prints no corpus totals: they size our pile, not the finding", () => {
    render(<Hero stats={stats()} />);

    expect(screen.queryByText(/172,404/)).not.toBeInTheDocument();
    expect(screen.queryByText(/65,694/)).not.toBeInTheDocument();
    expect(screen.queryByText(/19,380/)).not.toBeInTheDocument();
  });

  it("names the cohort from the id-months the API derived, each with its own year", () => {
    render(<Hero stats={stats({ cohort_start: "2512", cohort_end: "2609" })} />);

    expect(screen.getByText(/from December 2025 to September 2026/)).toBeInTheDocument();
  });

  it("says one month when the cohort is one month", () => {
    render(<Hero stats={stats({ cohort_start: "2608", cohort_end: "2608" })} />);

    expect(screen.getByText(/posted in August 2026/)).toBeInTheDocument();
  });

  it("degrades to a neutral phrase on an empty graph", () => {
    render(<Hero stats={stats({ cohort_start: null, cohort_end: null })} />);

    expect(screen.getByText(/in the indexed months/)).toBeInTheDocument();
  });
});
