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
    license: null,
    ...overrides,
  };
}

describe("CatalogResults", () => {
  it("names and links a CC licence beside the crop it is granted on", () => {
    render(
      <CatalogResults
        papers={[
          paper({
            title: "Shared under CC",
            license: "http://creativecommons.org/licenses/by-nc-sa/4.0/",
          }),
        ]}
        total={1}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    const notice = screen.getByRole("link", { name: "CC BY-NC-SA 4.0" });
    expect(notice).toHaveAttribute("href", "https://creativecommons.org/licenses/by-nc-sa/4.0/");
    // Its own target, not swallowed by the card-wide title link.
    expect(notice).not.toContainElement(screen.getByRole("link", { name: /Shared under CC/ }));
  });

  it("prints no licence notice for the arXiv default, which grants nothing to name", () => {
    render(
      <CatalogResults
        papers={[
          paper({
            title: "Default licence",
            license: "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
          }),
        ]}
        total={1}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("asks for every card's image by id, and lets a miss fall back to the glyph", () => {
    render(
      <CatalogResults
        papers={[paper({ arxiv_id: "2607.00001" })]}
        total={1}
        state={EMPTY_FILTER}
        loading={false}
        onLoadMore={null}
      />,
    );

    // Derived from the id, not read off the wire: the server renders the
    // crop on first request, so nothing here can know whether one exists
    // yet, and a field that claimed to would go stale (D19).
    const image = document.querySelector("img");
    expect(image).toHaveAttribute("src", "/thumbs/2607.00001.jpg");
    expect(image).toHaveAttribute("loading", "lazy");
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
