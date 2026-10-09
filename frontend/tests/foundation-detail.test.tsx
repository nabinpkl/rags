import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FoundationDetail } from "@/components/landing/foundation-detail";
import type { Foundation } from "@/lib/api-client";

const { fetchFoundationMock } = vi.hoisted(() => ({ fetchFoundationMock: vi.fn() }));
vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchFoundation: fetchFoundationMock,
}));

// The reading surface is mocked down to the id it was handed: its own
// behaviour (metadata resolution, the §6b link-back, the PDF frame) is
// covered by tests/paper-reader-panel.test.tsx. What matters here is WHICH
// paper each control opens.
vi.mock("@/components/landing/paper-reader-panel", () => ({
  PaperReaderPanel: ({ arxivId }: { arxivId: string }) => <div data-testid="reader">{arxivId}</div>,
}));

const PPO: Foundation = {
  arxiv_id: "1707.06347",
  title: "Proximal Policy Optimization Algorithms",
  authors: "John Schulman",
  primary_category: "cs.LG",
  year: 2017,
  version: "v2",
  cited_by: 536,
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderDetail() {
  return render(<FoundationDetail foundation={PPO} onBack={vi.fn()} onAsk={vi.fn()} />, {
    wrapper,
  });
}

afterEach(() => fetchFoundationMock.mockReset());

describe("FoundationDetail", () => {
  it("shows every citer as the count and only the indexed ones as the list (D16)", async () => {
    // THE line: 536 papers cite PPO; we indexed 2. The page must say both,
    // and must never imply the list is the whole set.
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [],
      indexed_citers: [
        { arxiv_id: "2608.00002", title: "Second", primary_category: "cs.LG", version: "v1" },
        { arxiv_id: "2608.00001", title: "First", primary_category: "cs.CL", version: "v1" },
      ],
    });

    renderDetail();

    expect(await screen.findByText(/Showing 2 of the 2 papers we indexed/)).toBeInTheDocument();
    expect(screen.getByText(/536 cite it in all/)).toBeInTheDocument();
    expect(screen.getByText("536")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("opens an indexed citer in the reader beside the lists, not on another page", async () => {
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 1,
      scope_size: 2,
      co_cited: [],
      indexed_citers: [
        { arxiv_id: "2608.00001", title: "First", primary_category: "cs.CL", version: "v1" },
      ],
    });

    renderDetail();

    fireEvent.click(await screen.findByRole("button", { name: "First" }));

    expect(screen.getByTestId("reader")).toHaveTextContent("2608.00001");
    expect(screen.getByRole("listitem")).toHaveAttribute("aria-current", "true");
  });

  it("version-pins the arXiv link for the foundation itself (D9)", async () => {
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 0,
      scope_size: 0,
      co_cited: [],
      indexed_citers: [],
    });

    renderDetail();

    const link = await screen.findByRole("link", { name: /arXiv:1707.06347v2/ });
    expect(link).toHaveAttribute("href", "https://arxiv.org/abs/1707.06347v2");
  });

  it("has the foundation open in the reader before anything is clicked", async () => {
    // The view is about this paper, so reading it is not a second
    // destination to go find.
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [],
      indexed_citers: [],
    });

    renderDetail();

    expect(screen.getByTestId("reader")).toHaveTextContent("1707.06347");
    expect(screen.queryByRole("link", { name: /read the paper/i })).not.toBeInTheDocument();
    await screen.findByText(/536 cite it in all/);
  });

  it("opens a co-cited work in the reader even though we may hold no text for it", async () => {
    // Most co-cited works are outside the frontier manifest. The reader still
    // shows their PDF (arxiv-pdf-frame.tsx fetches arxiv.org from the
    // browser), so one control covers both lists on this view.
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [
        { arxiv_id: "1409.1556", title: "Very Deep ConvNets", version: "v6", cite_both: 9 },
      ],
      indexed_citers: [],
    });

    renderDetail();

    fireEvent.click(await screen.findByRole("button", { name: "Very Deep ConvNets" }));

    expect(screen.getByTestId("reader")).toHaveTextContent("1409.1556");
  });

  it("returns the reader to the foundation from its heading", async () => {
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [
        { arxiv_id: "1409.1556", title: "Very Deep ConvNets", version: "v6", cite_both: 9 },
      ],
      indexed_citers: [],
    });

    renderDetail();

    fireEvent.click(await screen.findByRole("button", { name: "Very Deep ConvNets" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Proximal Policy Optimization Algorithms" }),
    );

    expect(screen.getByTestId("reader")).toHaveTextContent("1707.06347");
  });

  it("labels co-citation as counted, not clustered", async () => {
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [{ arxiv_id: "2402.03300", title: "DeepSeekMath", version: "v3", cite_both: 247 }],
      indexed_citers: [],
    });

    renderDetail();

    expect(await screen.findByText("247 papers cite both")).toBeInTheDocument();
    expect(screen.getByText("How many of our papers cite both.")).toBeInTheDocument();
  });

  it("disables the ask surface when the claim owns no indexed papers", async () => {
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 2,
      co_cited: [],
      indexed_citers: [],
    });

    renderDetail();

    expect(await screen.findByText(/no indexed papers for this claim yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask about these papers/i })).toBeDisabled();
  });

  it("never implies the agent read only the papers listed", async () => {
    // The bug this guards: the copy used indexed_citers.length for both the
    // list and the scope, so every foundation claimed the agent read 8 papers
    // when it actually read 14-46.
    fetchFoundationMock.mockResolvedValue({
      foundation: PPO,
      total_citers: 536,
      scope_size: 46,
      co_cited: [],
      indexed_citers: [
        { arxiv_id: "2608.00001", title: "First", primary_category: "cs.CL", version: "v1" },
      ],
    });

    renderDetail();

    expect(
      await screen.findByText(/answers come from the 46 papers we indexed/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Showing 1 of the 46 papers we indexed/)).toBeInTheDocument();
    expect(screen.getByText(/536 cite it in all/)).toBeInTheDocument();
  });
});
