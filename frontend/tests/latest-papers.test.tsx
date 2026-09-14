import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LatestPapers } from "@/components/landing/latest-papers";
import type { LatestResponse } from "@/lib/api-client";

const papers: LatestResponse["papers"] = [
  {
    arxiv_id: "2608.13560",
    title: "AutoDesign: Meta-Harness Optimization",
    authors: "A. Author and B. Writer",
    primary_category: "cs.CL",
    published: "2026-08-13",
    version: "v1",
    ref_count: 30,
  },
  {
    arxiv_id: "2608.13558",
    title: "OmniScientist",
    authors: null,
    primary_category: null,
    published: "2026-08-12",
    version: null,
    ref_count: 1,
  },
];

describe("LatestPapers", () => {
  it("links every row to the reader — nothing listed may dead-end (D16)", () => {
    render(<LatestPapers papers={papers} />);

    const link = screen.getByRole("link", { name: "AutoDesign: Meta-Harness Optimization" });
    expect(link).toHaveAttribute("href", "/app?paper=2608.13560");
  });

  it("states the date, category, and reference count per row", () => {
    render(<LatestPapers papers={papers} />);

    expect(screen.getByText(/13 Aug 2026/)).toBeInTheDocument();
    expect(screen.getByText(/12 Aug 2026/)).toBeInTheDocument();
    expect(screen.getByText(/cs\.CL/)).toBeInTheDocument();
    expect(screen.getByText(/30 refs/)).toBeInTheDocument();
    expect(screen.getByText(/1 ref/)).toBeInTheDocument();
    expect(screen.getByText(/uncategorized/)).toBeInTheDocument();
  });

  it("says freshness follows the index run, not the clock", () => {
    render(<LatestPapers papers={papers} />);

    expect(screen.getByText(/once the index run covers them/)).toBeInTheDocument();
  });

  it("renders nothing with no papers", () => {
    const { container } = render(<LatestPapers papers={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
