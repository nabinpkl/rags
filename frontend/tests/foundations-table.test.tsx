import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FoundationsTable } from "@/components/landing/foundations-table";
import type { Foundation, LandingResponse } from "@/lib/api-client";

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

const FOUNDATIONS: Foundation[] = [
  {
    arxiv_id: "2505.09388",
    title: "Qwen3 Technical Report",
    authors: "An Yang, Anfeng Li, Baosong Yang +57",
    primary_category: "cs.CL",
    year: 2025,
    version: "v1",
    cited_by: 1175,
  },
  {
    arxiv_id: "1707.06347",
    title: "Proximal Policy Optimization Algorithms",
    authors: "John Schulman",
    primary_category: "cs.LG",
    year: 2017,
    version: "v2",
    cited_by: 536,
  },
  {
    arxiv_id: "9999.99999",
    title: null,
    authors: null,
    primary_category: null,
    year: null,
    version: null,
    cited_by: 3,
  },
];

describe("FoundationsTable", () => {
  it("renders the ranking in order with its counts", () => {
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows[0]).toHaveTextContent("Qwen3 Technical Report");
    expect(rows[0]).toHaveTextContent("1175");
    expect(rows[1]).toHaveTextContent("Proximal Policy Optimization Algorithms");
  });

  it("renders the author list the API sent, already trimmed there", () => {
    // The trim happens server-side (config.landing_max_authors): untrimmed,
    // author strings were 94% of the /api/landing payload.
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    expect(screen.getByText(/An Yang, Anfeng Li, Baosong Yang \+57/)).toBeInTheDocument();
  });

  it("says so when the catalog has no record, rather than showing a blank row", () => {
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    expect(screen.getByText(/not in the catalog snapshot \(9999.99999\)/)).toBeInTheDocument();
  });

  it("opens the evidence on click", () => {
    const onSelect = vi.fn();
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Proximal Policy Optimization Algorithms"));

    expect(onSelect).toHaveBeenCalledWith(FOUNDATIONS[1]);
  });

  it("opens the evidence from the keyboard — rows are reachable without a pointer", () => {
    const onSelect = vi.fn();
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={onSelect} />);

    const row = screen.getAllByRole("row")[1];
    fireEvent.keyDown(row, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledWith(FOUNDATIONS[0]);
  });

  it("names the denominator the ranking is against", () => {
    render(<FoundationsTable stats={STATS} foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    expect(screen.getByText(/15,905 papers we parsed cite them/)).toBeInTheDocument();
    expect(screen.getByText(/top 3 of 63,457 cited works/)).toBeInTheDocument();
  });
});
