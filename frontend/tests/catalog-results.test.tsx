import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_FILTER } from "@/components/catalog/catalog-filters";
import { CatalogResults } from "@/components/catalog/catalog-results";
import type { NextPage } from "@/hooks/use-infinite-virtual-list";
import type { CatalogPaper } from "@/lib/api-client";

const LAST_PAGE: NextPage = {
  hasNextPage: false,
  isFetchingNextPage: false,
  isFetchNextPageError: false,
  fetchNextPage: () => {},
};

// The list windows against a scroller, so it needs a real element with a
// height. jsdom lays nothing out and reports 0, which would leave the window
// empty; the virtualizer reads `offsetHeight`, so that is what is given.
function scroller() {
  const element = document.body.appendChild(document.createElement("main"));
  Object.defineProperty(element, "offsetHeight", { value: 800 });
  Object.defineProperty(element, "offsetWidth", { value: 900 });
  return element;
}

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
        page={LAST_PAGE}
        scrollElement={scroller()}
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
        page={LAST_PAGE}
        scrollElement={scroller()}
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
        page={LAST_PAGE}
        scrollElement={scroller()}
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
        page={LAST_PAGE}
        scrollElement={scroller()}
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
        page={LAST_PAGE}
        scrollElement={scroller()}
      />,
    );

    expect(screen.getByLabelText("Pinned — Open on arXiv")).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/2608.00001v3",
    );
  });

  it("says where each card sits in the whole result, since most are not in the DOM", () => {
    render(
      <CatalogResults
        papers={[paper()]}
        total={12_345}
        state={EMPTY_FILTER}
        loading={false}
        page={{ ...LAST_PAGE, hasNextPage: true }}
        scrollElement={scroller()}
      />,
    );

    const item = screen.getByRole("listitem");
    expect(item).toHaveAttribute("aria-setsize", "12345");
    expect(item).toHaveAttribute("aria-posinset", "1");
    expect(screen.getByText("1 of 12,345")).toBeInTheDocument();
  });

  it("stops at a failed page and offers the retry, rather than asking again by itself", () => {
    const fetchNextPage = vi.fn();
    render(
      <CatalogResults
        papers={[paper()]}
        total={40}
        state={EMPTY_FILTER}
        loading={false}
        page={{ ...LAST_PAGE, hasNextPage: true, isFetchNextPageError: true, fetchNextPage }}
        scrollElement={scroller()}
      />,
    );

    expect(fetchNextPage).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("after 1 of 40 did not load");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("asks for the next page once the reader is near the end of what loaded", () => {
    const fetchNextPage = vi.fn();
    render(
      <CatalogResults
        papers={[paper()]}
        total={40}
        state={EMPTY_FILTER}
        loading={false}
        page={{ ...LAST_PAGE, hasNextPage: true, fetchNextPage }}
        scrollElement={scroller()}
      />,
    );

    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("says the end is the end", () => {
    render(
      <CatalogResults
        papers={[paper()]}
        total={1}
        state={EMPTY_FILTER}
        loading={false}
        page={LAST_PAGE}
        scrollElement={scroller()}
      />,
    );

    expect(screen.getByText("All 1 shown")).toBeInTheDocument();
  });

  it("goes back to the top when the filter changes, before the new rows arrive", () => {
    const canvas = scroller();
    canvas.scrollTop = 14_000;
    const { rerender } = render(
      <CatalogResults
        papers={[paper()]}
        total={40}
        state={EMPTY_FILTER}
        loading={false}
        page={LAST_PAGE}
        scrollElement={canvas}
      />,
    );
    expect(canvas.scrollTop).toBe(14_000);

    rerender(
      <CatalogResults
        papers={[]}
        total={0}
        state={{ ...EMPTY_FILTER, q: "diffusion" }}
        loading
        page={LAST_PAGE}
        scrollElement={canvas}
      />,
    );
    expect(canvas.scrollTop).toBe(0);
  });

  it("explains an empty result instead of showing an empty box", () => {
    render(
      <CatalogResults
        papers={[]}
        total={0}
        state={EMPTY_FILTER}
        loading={false}
        page={LAST_PAGE}
        scrollElement={scroller()}
      />,
    );

    expect(screen.getByText(/Nothing in the catalog matches that/)).toBeInTheDocument();
  });
});
