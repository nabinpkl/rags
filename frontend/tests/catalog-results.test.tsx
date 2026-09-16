import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EMPTY_FILTER } from "@/components/catalog/catalog-filters";
import { CatalogResults } from "@/components/catalog/catalog-results";
import type { CatalogPaper } from "@/lib/api-client";

function paper(overrides: Partial<CatalogPaper> = {}): CatalogPaper {
  return {
    arxiv_id: "2608.00001",
    title: "A paper",
    authors: "A. Author",
    abstract: "An abstract.",
    primary_category: "cs.CL",
    published: "2026-08-03",
    version: "v2",
    has_text: true,
    indexed: false,
    cited_by: 0,
    thumbnail: null,
    ...overrides,
  };
}

describe("CatalogResults", () => {
  it("shows a crop when the licence allowed one and the glyph when it did not", () => {
    render(
      <CatalogResults
        papers={[
          paper({ arxiv_id: "2607.00001", title: "With a crop", thumbnail: "2026/07/a.jpg" }),
          paper({ arxiv_id: "2608.00002", title: "Without one" }),
        ]}
        total={2}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    const images = document.querySelectorAll("img");
    expect(images).toHaveLength(1);
    expect(images[0]).toHaveAttribute("src", "/thumbs/2026/07/a.jpg");
  });

  it("sends an indexed paper to the reader and everything else to arXiv", () => {
    render(
      <CatalogResults
        papers={[
          paper({ arxiv_id: "2607.00001", title: "Indexed one", indexed: true }),
          paper({ arxiv_id: "2608.00002", title: "Catalog one" }),
        ]}
        total={2}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    expect(screen.getByLabelText("Indexed one — Open in the reader")).toHaveAttribute(
      "href",
      "/app?paper=2607.00001",
    );
    expect(screen.getByLabelText("Catalog one — Open on arXiv")).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/2608.00002v2",
    );
  });

  it("pins the arXiv link to the version we recorded (§6b)", () => {
    render(
      <CatalogResults
        papers={[paper({ title: "Pinned", version: "v3" })]}
        total={1}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    expect(screen.getByLabelText("Pinned — Open on arXiv")).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/2608.00001v3",
    );
  });

  it("counts what is left rather than what has loaded", () => {
    render(
      <CatalogResults
        papers={[paper()]}
        total={12_345}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Show more (12,344 left)" })).toBeInTheDocument();
  });

  it("explains an empty result instead of showing an empty box", () => {
    render(
      <CatalogResults
        papers={[]}
        total={0}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    expect(screen.getByText(/Nothing in the catalog matches that/)).toBeInTheDocument();
  });
});
