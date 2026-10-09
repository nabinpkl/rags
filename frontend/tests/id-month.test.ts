import { describe, expect, it } from "vitest";

import { formatIdMonth, formatIdMonthRange } from "@/lib/id-month";

describe("formatIdMonth", () => {
  it("reads an arXiv id-month as a month and a year", () => {
    expect(formatIdMonth("2608")).toBe("August 2026");
    expect(formatIdMonth("2608", "short")).toBe("Aug 2026");
  });

  it("keeps the century the id implies — the window reaches back to 2007", () => {
    expect(formatIdMonth("0711")).toBe("November 2007");
  });
});

describe("formatIdMonthRange", () => {
  it("spans the window with each side carrying its own year", () => {
    expect(formatIdMonthRange("0711", "2609")).toBe("Nov 2007 – Sep 2026");
  });

  it("collapses a one-month window rather than repeating the month", () => {
    expect(formatIdMonthRange("2608", "2608")).toBe("Aug 2026");
  });

  it("returns null on an empty graph, so the caller renders nothing", () => {
    expect(formatIdMonthRange(null, "2608")).toBeNull();
    expect(formatIdMonthRange("2608", null)).toBeNull();
  });
});
