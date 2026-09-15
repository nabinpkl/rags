import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MethodsNote } from "@/components/landing/methods-note";
import type { LandingResponse } from "@/lib/api-client";

const STATS: LandingResponse["stats"] = {
  cohort_start: "2607",
  cohort_end: "2608",
  cohort_papers: 19380,
  cohort_catalog_papers: 27507,
  corpus_papers: 57206,
  papers_parsed: 18844,
  papers_with_references: 15905,
  citations: 162792,
  cited_works: 63457,
};

const CITED_YEARS: LandingResponse["cited_years"] = [
  { year: 2018, citations: 10 },
  { year: 2020, citations: 10 },
  { year: 2024, citations: 40 },
  { year: 2025, citations: 30 },
  { year: null, citations: 10 },
];

describe("MethodsNote", () => {
  it("counts the parse rate over papers that reached the parser, not every catalog row", () => {
    // THE bug: 15,905 over the whole corpus (57,206) printed a 30% parse rate
    // for a parser that yields 84%, and then blamed the missing 70% on
    // reference lists that "did not parse" when those papers were never
    // collected at all.
    render(<MethodsNote stats={STATS} citedYears={CITED_YEARS} />);

    expect(
      screen.getByText(
        /15,905 of the 18,844 papers we extracted text from yielded a usable list — 84%/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/did not parse are missing entirely/)).toHaveTextContent("16%");
  });

  it("names the wider corpus instead of letting the cohort stand for all of it", () => {
    render(<MethodsNote stats={STATS} citedYears={CITED_YEARS} />);

    expect(screen.getByText(/57,206 papers/)).toBeInTheDocument();
    expect(screen.getByText(/it is not a census/)).toBeInTheDocument();
  });

  it("keeps the clustering-stability finding on the page", () => {
    // This paragraph is the REASON the page has no theme cards. Without it the
    // design reads as an omission rather than a decision.
    render(<MethodsNote stats={STATS} citedYears={CITED_YEARS} />);

    expect(
      screen.getByText(/two runs of the same clustering agree on only 43–61% of pairs/),
    ).toBeInTheDocument();
  });

  it("measures reach against the cohort's own year, not a round number", () => {
    // The cohort ends in 2608, so the year is 2026: every bucket here (2018,
    // 2020, 2024, 2025, undated) is earlier, so 100% predates it.
    render(<MethodsNote stats={STATS} citedYears={CITED_YEARS} />);

    expect(
      screen.getByText(/100% of these citations point at work published before 2026/),
    ).toBeInTheDocument();
  });

  it("says so plainly when there is nothing to place in time", () => {
    render(<MethodsNote stats={STATS} citedYears={[]} />);

    expect(screen.getByText(/No citations to place in time yet/)).toBeInTheDocument();
  });

  it("says the page defines the index, not the other way round", () => {
    render(<MethodsNote stats={STATS} citedYears={CITED_YEARS} />);

    expect(screen.getByText(/The page defines what is indexed/)).toBeInTheDocument();
  });

  it("survives an empty graph without dividing by zero", () => {
    render(
      <MethodsNote
        stats={{ ...STATS, papers_parsed: 0, papers_with_references: 0 }}
        citedYears={[]}
      />,
    );

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
