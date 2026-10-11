// The catalog filter's URL half. Explore and the RAG demo share it. The
// view's scope never reaches, and is never read from, the URL, so a
// hand-edited link cannot widen the demo past the papers its agent reads.
import { describe, expect, it } from "vitest";

import { EMPTY_FILTER } from "@/components/catalog/catalog-filters";
import { catalogSearchParams, mergeCatalogFilter } from "@/hooks/use-catalog-query";

describe("catalogSearchParams", () => {
  it("omits every resting value", () => {
    expect(catalogSearchParams(EMPTY_FILTER).toString()).toBe("");
  });

  it("writes the reader's choices", () => {
    const state = { ...EMPTY_FILTER, q: "rag", category: "cs.CL", sort: "cited" as const };
    expect(catalogSearchParams(state).toString()).toBe("q=rag&category=cs.CL&sort=cited");
  });

  it("never writes the view's scope", () => {
    const state = { ...EMPTY_FILTER, category: "cs.CL", holding: "indexed" as const };
    expect(catalogSearchParams(state).toString()).toBe("category=cs.CL");
  });
});

describe("mergeCatalogFilter", () => {
  it("falls back from relevance when the query goes away", () => {
    const state = { ...EMPTY_FILTER, q: "rag", sort: "relevance" as const };
    expect(mergeCatalogFilter(state, { q: "" }).sort).toBe("newest");
  });

  it("picks relevance for a first query, and keeps a chosen order after that", () => {
    expect(mergeCatalogFilter(EMPTY_FILTER, { q: "rag" }).sort).toBe("relevance");
    const chosen = { ...EMPTY_FILTER, q: "rag", sort: "cited" as const };
    expect(mergeCatalogFilter(chosen, { q: "retrieval" }).sort).toBe("cited");
  });
});
