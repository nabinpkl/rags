// On a phone the facet rail is a sheet over the list it filters: a tap
// applies instantly, but the result is hidden behind the sheet. The way out
// has to say what is waiting — the filtered count — and actually close it.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { FacetFilters } from "@/components/explorer/facet-filters";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";
import { useFacetsQuery } from "@/hooks/use-papers-query";

vi.mock("@/hooks/use-papers-query", () => ({
  useFacetsQuery: vi.fn(),
}));

const useFacetsQueryMock = vi.mocked(useFacetsQuery);

function mockFacets(total: number) {
  useFacetsQueryMock.mockReturnValue({
    data: {
      total,
      category: { buckets: [{ value: "cs.CL", count: total }] },
      year: { buckets: [{ value: 2026, count: total }] },
    },
  } as unknown as ReturnType<typeof useFacetsQuery>);
}

beforeEach(() => {
  useViewerStore.getState().reset();
  useUiShellStore.setState({ overlay: "filters" });
  useFacetsQueryMock.mockReset();
});

describe("FacetFilters", () => {
  it("closes the drawer from a button that names the filtered count", () => {
    mockFacets(85);
    render(<FacetFilters />);
    const done = screen.getByRole("button", { name: /show 85 papers/i });
    fireEvent.click(done);
    expect(useUiShellStore.getState().overlay).toBe("none");
  });

  it("still offers a way out before the facets have loaded", () => {
    useFacetsQueryMock.mockReturnValue({ data: undefined } as ReturnType<typeof useFacetsQuery>);
    render(<FacetFilters />);
    fireEvent.click(screen.getByRole("button", { name: /^show papers$/i }));
    expect(useUiShellStore.getState().overlay).toBe("none");
  });

  it("keeps the done button out of the docked rail", () => {
    mockFacets(200);
    render(<FacetFilters />);
    // The rail docks by viewport (`md:`), so the button is hidden by the same
    // breakpoint rather than by a container query — the two must agree.
    expect(
      screen.getByRole("button", { name: /show 200 papers/i }).parentElement?.className,
    ).toMatch(/md:hidden/);
  });
});
