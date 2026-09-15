import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeroStats } from "@/components/landing/hero-stats";
import type { LandingResponse } from "@/lib/api-client";

function stats(overrides: Partial<LandingResponse["stats"]> = {}): LandingResponse["stats"] {
  return {
    cohort_start: "2607",
    cohort_end: "2608",
    cohort_papers: 19380,
    cohort_catalog_papers: 27507,
    corpus_papers: 57206,
    papers_parsed: 20733,
    papers_with_references: 16893,
    citations: 172404,
    cited_works: 65694,
    ...overrides,
  };
}

describe("HeroStats", () => {
  it("shows the four counted facts, grouped for readability", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText("19,380")).toBeInTheDocument();
    expect(screen.getByText("16,893")).toBeInTheDocument();
    expect(screen.getByText("172,404")).toBeInTheDocument();
    expect(screen.getByText("65,694")).toBeInTheDocument();
  });

  it("claims a measured share of arXiv, never 'every paper'", () => {
    // The page said "every cs paper arXiv posted in the window". Measured,
    // that was 94% of July 2026, 49% of August and 5% of September.
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText(/19,380 of the 27,507 cs papers/)).toBeInTheDocument();
    expect(screen.queryByText(/every cs paper/)).not.toBeInTheDocument();
    // The same denominator rides on the KPI label, since a six-figure number
    // under a bare "cs papers" reads as the field's output.
    expect(screen.getByText(/of 27,507 cs papers arXiv posted then/)).toBeInTheDocument();
  });

  it("drops the share rather than the honesty when the catalog cannot answer", () => {
    render(<HeroStats stats={stats({ cohort_catalog_papers: null })} />);

    expect(screen.getByText(/19,380 cs papers/)).toBeInTheDocument();
    expect(screen.queryByText(/of the/)).not.toBeInTheDocument();
    expect(screen.getByText(/cs papers in the cohort months/)).toBeInTheDocument();
  });

  it("names the cohort from the id-months the API derived, not a hardcoded date", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText(/posted between July 2026 and August 2026/)).toBeInTheDocument();
  });

  it("gives each side its own year, since the two need not share one", () => {
    render(<HeroStats stats={stats({ cohort_start: "2512", cohort_end: "2609" })} />);

    expect(screen.getByText(/between December 2025 and September 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/December and September 2026/)).not.toBeInTheDocument();
  });

  it("says one month when the cohort is one month, with the preposition to match", () => {
    // The preposition travels with the span: a fixed "in" in the sentence
    // plus "between" from the formatter rendered "posted in between July...".
    render(<HeroStats stats={stats({ cohort_start: "2608", cohort_end: "2608" })} />);

    expect(screen.getByText(/posted in August 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/August 2026 and August 2026/)).not.toBeInTheDocument();
  });

  it("degrades to a neutral phrase on an empty graph rather than rendering NaN", () => {
    render(<HeroStats stats={stats({ cohort_start: null, cohort_end: null })} />);

    expect(screen.getByText(/in the indexed months/)).toBeInTheDocument();
  });

  it("states the method in the lede: counted, not modelled", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText(/No topic modelling, no clustering/)).toBeInTheDocument();
  });
});
