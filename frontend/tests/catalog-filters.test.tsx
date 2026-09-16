import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CatalogFilters, type CatalogFilterState } from "@/components/catalog/catalog-filters";
import type { CatalogFacetsResponse } from "@/lib/api-client";

const STATE: CatalogFilterState = {
  q: "",
  category: null,
  month: null,
  holding: "all",
  sort: "newest",
};

const FACETS: CatalogFacetsResponse = {
  holdings: [
    { value: "all", papers: 65_503 },
    { value: "text", papers: 29_027 },
    { value: "indexed", papers: 811 },
  ],
  categories: [
    { value: "cs.CV", papers: 12_430 },
    { value: "cs.LG", papers: 11_209 },
  ],
  months: [
    { value: "2608", papers: 14_489 },
    { value: "2607", papers: 13_010 },
  ],
  total: 65_503,
};

describe("CatalogFilters", () => {
  it("shows what each choice would give, not what the current filter gave", () => {
    render(<CatalogFilters state={STATE} facets={FACETS} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: /cs\.CV 12,430/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Aug 2026 14,489/ })).toBeInTheDocument();
  });

  it("clears a value that is clicked while already selected", () => {
    const onChange = vi.fn();
    render(
      <CatalogFilters
        state={{ ...STATE, category: "cs.CV" }}
        facets={FACETS}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /cs\.CV 12,430/ }));

    expect(onChange).toHaveBeenCalledWith({ category: null });
  });

  it("disables ranking by match until there is something to match", () => {
    const { rerender } = render(
      <CatalogFilters state={STATE} facets={FACETS} onChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Best match" })).toBeDisabled();

    rerender(
      <CatalogFilters state={{ ...STATE, q: "diffusion" }} facets={FACETS} onChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Best match" })).toBeEnabled();
  });

  it("commits the search box on a pause, not on every keystroke", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<CatalogFilters state={STATE} facets={FACETS} onChange={onChange} />);

    const box = screen.getByLabelText("Search titles and abstracts");
    fireEvent.change(box, { target: { value: "dif" } });
    fireEvent.change(box, { target: { value: "diffusion" } });
    expect(onChange).not.toHaveBeenCalled();

    vi.advanceTimersByTime(400);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ q: "diffusion" });
    vi.useRealTimers();
  });

  it("holds the long tail of months behind one click instead of drawing 234", () => {
    const months = Array.from({ length: 234 }, (_, i) => ({
      value: String(2600 + i),
      papers: 234 - i,
    }));
    render(<CatalogFilters state={STATE} facets={{ ...FACETS, months }} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "224 more" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "224 more" }));
    expect(screen.getByRole("button", { name: "Show fewer" })).toBeInTheDocument();
  });

  it("keeps a chosen value visible even when it ranks below the cut", () => {
    // 36 real id-months, largest first, so the chosen one sits well past the
    // twelve the row draws.
    const months = [24, 25, 26]
      .flatMap((year) =>
        Array.from({ length: 12 }, (_, m) => `${year}${String(m + 1).padStart(2, "0")}`),
      )
      .map((value, i, all) => ({ value, papers: all.length - i }));
    const last = months[months.length - 1];
    render(
      <CatalogFilters
        state={{ ...STATE, month: last.value }}
        facets={{ ...FACETS, months }}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Dec 2026 1" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders no chip row at all when the facets have not arrived", () => {
    render(<CatalogFilters state={STATE} facets={undefined} onChange={() => {}} />);

    expect(screen.queryByText("Field")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Search titles and abstracts")).toBeInTheDocument();
  });
});
