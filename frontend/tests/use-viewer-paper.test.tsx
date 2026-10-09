// Every paper link on the dashboard points at the reader, including works we
// only know as citation targets. What makes that safe is this hook: the corpus
// answers when it can, the citation graph answers when it cannot, and `indexed`
// is derived from WHICH answered — never read off a response field (D16).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useViewerPaper } from "@/hooks/use-viewer-paper";
import { ApiError } from "@/lib/api-client";

const { fetchPaperDetailMock, fetchFoundationMock } = vi.hoisted(() => ({
  fetchPaperDetailMock: vi.fn(),
  fetchFoundationMock: vi.fn(),
}));
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchPaperDetail: fetchPaperDetailMock,
  fetchFoundation: fetchFoundationMock,
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const CORPUS_PAPER = {
  arxiv_id: "2608.00001",
  title: "A paper we hold",
  authors: "A. Author",
  abstract: "",
  categories: "cs.CL",
  primary_category: "cs.CL",
  year: 2026,
  published: "2026-08-01",
  venue: null,
  license: null,
  version: "v1",
  facets: {},
  n_chunks: 12,
  excerpts: [],
  excerpts_truncated: false,
};

const CITED_WORK = {
  foundation: {
    arxiv_id: "1409.1556",
    title: "Very Deep Convolutional Networks",
    authors: "K. Simonyan",
    primary_category: "cs.CV",
    year: 2014,
    version: "v6",
    cited_by: 91,
  },
  co_cited: [],
  indexed_citers: [],
  total_citers: 91,
  scope_size: 0,
};

afterEach(() => {
  fetchPaperDetailMock.mockReset();
  fetchFoundationMock.mockReset();
});

describe("useViewerPaper", () => {
  it("takes the corpus record when we hold the paper, and never asks the graph", async () => {
    fetchPaperDetailMock.mockResolvedValue(CORPUS_PAPER);

    const { result } = renderHook(() => useViewerPaper("2608.00001"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.title).toBe("A paper we hold");
    expect(result.current.data?.indexed).toBe(true);
    expect(fetchFoundationMock).not.toHaveBeenCalled();
  });

  it("falls back to the citation graph for a work we cite but never held", async () => {
    fetchPaperDetailMock.mockRejectedValue(new ApiError("/api/papers/1409.1556", 404));
    fetchFoundationMock.mockResolvedValue(CITED_WORK);

    const { result } = renderHook(() => useViewerPaper("1409.1556"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    // The version matters most of all: it is what pins the PDF the reader's
    // browser fetches (§6b/D9).
    expect(result.current.data?.version).toBe("v6");
    expect(result.current.data?.title).toBe("Very Deep Convolutional Networks");
    expect(result.current.data?.indexed).toBe(false);
    expect(result.current.isError).toBe(false);
    // A 404 is an answer, not a failure: retrying it three times would only
    // hold the fallback back by seconds (use-paper-detail.ts).
    expect(fetchPaperDetailMock).toHaveBeenCalledTimes(1);
  });

  it("a not-indexed work carries no excerpts, whatever the graph returned", async () => {
    fetchPaperDetailMock.mockRejectedValue(new ApiError("/api/papers/1409.1556", 404));
    fetchFoundationMock.mockResolvedValue(CITED_WORK);

    const { result } = renderHook(() => useViewerPaper("1409.1556"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.excerpts).toEqual([]);
    expect(result.current.data?.excerpts_truncated).toBe(false);
  });

  it("errors only when neither record exists", async () => {
    fetchPaperDetailMock.mockRejectedValue(new ApiError("/api/papers/9999.99999", 404));
    fetchFoundationMock.mockRejectedValue(new ApiError("/api/foundations/9999.99999", 404));

    const { result } = renderHook(() => useViewerPaper("9999.99999"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
    // Neither 404 is retried: on the deployed site this was three seconds of
    // "Loading..." before the viewer would admit it had never heard of the id.
    expect(fetchPaperDetailMock).toHaveBeenCalledTimes(1);
    expect(fetchFoundationMock).toHaveBeenCalledTimes(1);
  });

  it("fetches nothing at all with no paper open", () => {
    renderHook(() => useViewerPaper(null), { wrapper });
    expect(fetchPaperDetailMock).not.toHaveBeenCalled();
    expect(fetchFoundationMock).not.toHaveBeenCalled();
  });
});
