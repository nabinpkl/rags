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
  it("is a sentence, not a KPI row", () => {
    // Four big numbers above the ranking read as the finding; the finding is
    // the ranking. The totals that size the sample stay, inside the sentence
    // that says what they are.
    const { container } = render(<Hero stats={stats()} />);

    expect(container.querySelector("dl")).toBeNull();
    expect(screen.queryByText("65,694")).not.toBeInTheDocument();
    expect(screen.queryByText("667")).not.toBeInTheDocument();
    expect(screen.queryByText(/papers the agent reads and quotes/)).not.toBeInTheDocument();
  });

  it("claims a measured share of arXiv, never 'every paper'", () => {
    // The page said "every cs paper arXiv posted in the window". Measured,
    // that was 94% of July 2026, 49% of August and 5% of September.
    render(<Hero stats={stats()} />);

    expect(screen.getByText(/19,380 of the 27,507 cs papers/)).toBeInTheDocument();
    expect(screen.queryByText(/every cs paper/)).not.toBeInTheDocument();
  });

  it("counts citations in the same breath as the papers they came from", () => {
    render(<Hero stats={stats()} />);

    expect(screen.getByText(/172,404 citations to other arXiv papers/)).toBeInTheDocument();
  });

  it("drops the share rather than the honesty when the catalog cannot answer", () => {
    render(<Hero stats={stats({ cohort_catalog_papers: null })} />);

    expect(screen.getByText(/19,380 cs papers/)).toBeInTheDocument();
    expect(screen.queryByText(/of the 27,507/)).not.toBeInTheDocument();
  });

  it("names the cohort from the id-months the API derived, not a hardcoded date", () => {
    render(<Hero stats={stats()} />);

    expect(screen.getByText(/posted between July 2026 and August 2026/)).toBeInTheDocument();
  });

  it("gives each side its own year, since the two need not share one", () => {
    render(<Hero stats={stats({ cohort_start: "2512", cohort_end: "2609" })} />);

    expect(screen.getByText(/between December 2025 and September 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/December and September 2026/)).not.toBeInTheDocument();
  });

  it("says one month when the cohort is one month, with the preposition to match", () => {
    // The preposition travels with the span: a fixed "in" in the sentence
    // plus "between" from the formatter rendered "posted in between July...".
    render(<Hero stats={stats({ cohort_start: "2608", cohort_end: "2608" })} />);

    expect(screen.getByText(/posted in August 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/August 2026 and August 2026/)).not.toBeInTheDocument();
  });

  it("degrades to a neutral phrase on an empty graph rather than rendering NaN", () => {
    render(<Hero stats={stats({ cohort_start: null, cohort_end: null })} />);

    expect(screen.getByText(/in the indexed months/)).toBeInTheDocument();
  });

  it("states the method in the lede: counted, not modelled", () => {
    render(<Hero stats={stats()} />);

    expect(screen.getByText(/No topic modelling, no clustering/)).toBeInTheDocument();
  });
});
