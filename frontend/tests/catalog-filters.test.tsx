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
    { value: "cs.CV", papers: 12_430, name: "Computer Vision and Pattern Recognition" },
    { value: "cs.LG", papers: 11_209, name: "Machine Learning" },
    { value: "quant-ph", papers: 40, name: null },
  ],
  months: [
    { value: "2608", papers: 14_489 },
    { value: "2607", papers: 13_010 },
  ],
  total: 65_503,
};

describe("CatalogFilters — the view's scope", () => {
  const INDEXED: CatalogFilterState = { ...STATE, holding: "indexed" };

  it("offers no control over what the view lists", () => {
    render(<CatalogFilters state={STATE} facets={FACETS} onChange={() => {}} />);
    expect(screen.queryByLabelText("Show")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Order")).toBeInTheDocument();
  });

  it("does not count the scope as a filter the reader chose", () => {
    const { rerender } = render(
      <CatalogFilters state={INDEXED} facets={FACETS} onChange={() => {}} />,
    );
    expect(screen.queryByRole("button", { name: "Clear the filter" })).not.toBeInTheDocument();

    rerender(
      <CatalogFilters
        state={{ ...INDEXED, category: "cs.CL" }}
        facets={FACETS}
        onChange={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Clear the filter" })).toBeInTheDocument();
  });
});

describe("CatalogFilters", () => {
  it("shows what each choice would give, not what the current filter gave", () => {
    render(<CatalogFilters state={STATE} facets={FACETS} onChange={() => {}} />);

    expect(
      within(screen.getByRole("list", { name: "Topic" })).getByRole("button", {
        name: /Computer Vision and Pattern Recognition/,
      }),
    );
    expect(
      within(screen.getByLabelText("Month posted")).getByRole("option", {
        name: "Aug 2026 · 14,489",
      }),
    );
  });

  it("narrows on a chosen value and clears on Any", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <CatalogFilters state={STATE} facets={FACETS} onChange={onChange} />,
    );

    fireEvent.change(screen.getByLabelText("Month posted"), { target: { value: "2608" } });
    expect(onChange).toHaveBeenCalledWith({ month: "2608" });

    rerender(
      <CatalogFilters state={{ ...STATE, month: "2608" }} facets={FACETS} onChange={onChange} />,
    );
    fireEvent.change(screen.getByLabelText("Month posted"), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith({ month: null });
  });

  it("narrows on a topic", () => {
    const onChange = vi.fn();
    render(<CatalogFilters state={STATE} facets={FACETS} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Machine Learning/ }));
    expect(onChange).toHaveBeenCalledWith({ category: "cs.LG" });
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

    expect(screen.queryByRole("list", { name: "Topic" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Month posted")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Order")).toBeInTheDocument();
  });
});
