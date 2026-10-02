import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FoundationsTable } from "@/components/landing/foundations-table";
import type { Foundation } from "@/lib/api-client";

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
    render(<FoundationsTable foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows[0]).toHaveTextContent("Qwen3 Technical Report");
    expect(rows[0]).toHaveTextContent("1,175");
    expect(rows[1]).toHaveTextContent("Proximal Policy Optimization Algorithms");
  });

  it("renders the author list the API sent, already trimmed there", () => {
    // The trim happens server-side (config.landing_max_authors): untrimmed,
    // author strings were 94% of the /api/landing payload.
    render(<FoundationsTable foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    expect(screen.getByText(/An Yang, Anfeng Li, Baosong Yang \+57/)).toBeInTheDocument();
  });

  it("says so when the catalog has no record, rather than showing a blank row", () => {
    render(<FoundationsTable foundations={FOUNDATIONS} onSelect={vi.fn()} />);

    expect(screen.getByText(/not in the catalog snapshot \(9999.99999\)/)).toBeInTheDocument();
  });

  it("opens the evidence on click", () => {
    const onSelect = vi.fn();
    render(<FoundationsTable foundations={FOUNDATIONS} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Proximal Policy Optimization Algorithms"));

    expect(onSelect).toHaveBeenCalledWith(FOUNDATIONS[1]);
  });

  it("opens the evidence from the keyboard — rows are reachable without a pointer", () => {
    const onSelect = vi.fn();
    render(<FoundationsTable foundations={FOUNDATIONS} onSelect={onSelect} />);

    const row = screen.getAllByRole("row")[1];
    fireEvent.keyDown(row, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledWith(FOUNDATIONS[0]);
  });
});
