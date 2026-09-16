import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecentUptake } from "@/components/landing/recent-uptake";
import type { UptakeResponse } from "@/lib/api-client";

function work(arxiv_id: string, title: string, citations_from: number, cited_by: number) {
  return {
    work: {
      arxiv_id,
      title,
      authors: "A. Author",
      primary_category: "cs.CL",
      year: 2026,
      version: "v1",
      cited_by,
    },
    citations_from,
  };
}

const UPTAKE: UptakeResponse = {
  from_month: "2607",
  to_month: "2608",
  works: [
    work("2607.02770", "Gemma 4 Technical Report", 92, 118),
    work("2607.24653", "Kimi K3", 37, 51),
  ],
  works_total: 1312,
  edges_total: 2061,
};

describe("RecentUptake", () => {
  it("names both months, so the window the count covers is on the page", () => {
    render(<RecentUptake uptake={UPTAKE} onSelect={() => {}} />);

    expect(screen.getByText("August 2026 citing July 2026")).toBeInTheDocument();
    expect(
      screen.getByText(/1,312 July 2026 papers drew 2,061 citations from August 2026 papers/),
    ).toBeInTheDocument();
  });

  it("shows the month's count beside the work's total, never one alone", () => {
    // 92 is the finding; 118 is what stops 92 being read as the whole of a
    // work's reception.
    render(<RecentUptake uptake={UPTAKE} onSelect={() => {}} />);

    expect(screen.getByText("92")).toBeInTheDocument();
    expect(screen.getByText(/118 citations in all/)).toBeInTheDocument();
  });

  it("opens the same detail view the ranking opens", () => {
    const onSelect = vi.fn();
    render(<RecentUptake uptake={UPTAKE} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /Gemma 4/ }));

    expect(onSelect).toHaveBeenCalledWith(UPTAKE.works[0]!.work);
  });

  it("renders nothing when no two complete months adjoin", () => {
    // The API answers with nulls rather than reaching for an incomplete
    // month; the panel has to disappear, not print an empty frame.
    const { container } = render(
      <RecentUptake
        uptake={{ from_month: null, to_month: null, works: [], works_total: 0, edges_total: 0 }}
        onSelect={() => {}}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
