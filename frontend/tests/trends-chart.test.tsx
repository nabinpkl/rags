import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendsChart } from "@/components/landing/trends-chart";
import type { TrendsResponse } from "@/lib/api-client";

function months(n: number, startYear = 2024, startMonth = 1): TrendsResponse["months"] {
  return Array.from({ length: n }, (_, i) => {
    const date = new Date(Date.UTC(startYear, startMonth - 1 + i, 1));
    const month = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
    return { month, papers_added: 100 + i, refs_made: 1000 + i * 10 };
  });
}

describe("TrendsChart", () => {
  it("states whole-span totals so the trailing window cannot mislead", () => {
    render(<TrendsChart months={months(30)} />);

    // 30 months of 100..129 papers and 1000..1290 refs.
    expect(screen.getByText(/3,435 papers/)).toBeInTheDocument();
    expect(screen.getByText(/34,350 references extracted/)).toBeInTheDocument();
  });

  it("charts only the trailing 12 months", () => {
    render(<TrendsChart months={months(30)} />);

    // First month (2024-01) falls off; the 19th (2025-07) is the oldest shown.
    expect(screen.queryByTitle(/2024-01/)).not.toBeInTheDocument();
    expect(screen.getByTitle(/2025-07: 118 papers arrived/)).toBeInTheDocument();
  });

  it("renders nothing with no months", () => {
    const { container } = render(<TrendsChart months={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
