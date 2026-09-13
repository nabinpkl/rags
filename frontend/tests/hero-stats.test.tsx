import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeroStats } from "@/components/landing/hero-stats";
import type { LandingResponse } from "@/lib/api-client";

function stats(overrides: Partial<LandingResponse["stats"]> = {}): LandingResponse["stats"] {
  return {
    window_start: "2607",
    window_end: "2608",
    papers_in_window: 18844,
    papers_with_references: 15905,
    citations: 162792,
    cited_works: 63457,
    ...overrides,
  };
}

describe("HeroStats", () => {
  it("shows the four counted facts, grouped for readability", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText("18,844")).toBeInTheDocument();
    expect(screen.getByText("15,905")).toBeInTheDocument();
    expect(screen.getByText("162,792")).toBeInTheDocument();
    expect(screen.getByText("63,457")).toBeInTheDocument();
  });

  it("names the window from the id-months the API derived, not a hardcoded date", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText(/July 2026 and August 2026/)).toBeInTheDocument();
  });

  it("gives each side its own year — the window spans decades", () => {
    render(<HeroStats stats={stats({ window_start: "0711", window_end: "2609" })} />);

    expect(screen.getByText(/November 2007 and September 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/November and September 2026/)).not.toBeInTheDocument();
  });

  it("says one month when the window is one month", () => {
    render(<HeroStats stats={stats({ window_start: "2608", window_end: "2608" })} />);

    expect(screen.getByText(/August 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/August and August/)).not.toBeInTheDocument();
  });

  it("degrades to a neutral phrase on an empty graph rather than rendering NaN", () => {
    render(<HeroStats stats={stats({ window_start: null, window_end: null })} />);

    expect(screen.getByText(/the indexed window/)).toBeInTheDocument();
  });

  it("states the method in the lede — counted, not modelled", () => {
    render(<HeroStats stats={stats()} />);

    expect(screen.getByText(/No topic modelling, no clustering/)).toBeInTheDocument();
  });
});
