import { fireEvent, render, screen, within } from "@testing-library/react";
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

    expect(within(screen.getByLabelText("Field")).getByRole("option", { name: "cs.CV · 12,430" }));
    expect(
      within(screen.getByLabelText("Month posted")).getByRole("option", {
        name: "Aug 2026 · 14,489",
      }),
    );
    expect(
      within(screen.getByLabelText("Show")).getByRole("option", {
        name: "The agent can read it · 811",
      }),
    );
  });

  it("narrows on a chosen value and clears on Any", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <CatalogFilters state={STATE} facets={FACETS} onChange={onChange} />,
    );

    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "cs.CV" } });
    expect(onChange).toHaveBeenCalledWith({ category: "cs.CV" });

    rerender(
      <CatalogFilters
        state={{ ...STATE, category: "cs.CV" }}
        facets={FACETS}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("Field"), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith({ category: null });
  });

  it("disables ranking by match until there is something to match", () => {
    const { rerender } = render(
      <CatalogFilters state={STATE} facets={FACETS} onChange={() => {}} />,
    );
    const order = screen.getByLabelText("Order");
    expect(within(order).getByRole("option", { name: "Best match" })).toBeDisabled();

    rerender(
      <CatalogFilters state={{ ...STATE, q: "diffusion" }} facets={FACETS} onChange={() => {}} />,
    );
    expect(within(order).getByRole("option", { name: "Best match" })).toBeEnabled();
  });

  it("offers every one of the 234 id-months rather than a head and an expander", () => {
    const months = Array.from({ length: 234 }, (_, i) => ({
      value: String(2600 + i),
      papers: 234 - i,
    }));
    render(<CatalogFilters state={STATE} facets={{ ...FACETS, months }} onChange={() => {}} />);

    // 234 months plus "Any month": the reason this is a select and not rows.
    expect(within(screen.getByLabelText("Month posted")).getAllByRole("option")).toHaveLength(235);
  });

  it("renders no facet control at all when the facets have not arrived", () => {
    render(<CatalogFilters state={STATE} facets={undefined} onChange={() => {}} />);

    expect(screen.queryByLabelText("Field")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Month posted")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Show")).toBeInTheDocument();
  });
});
