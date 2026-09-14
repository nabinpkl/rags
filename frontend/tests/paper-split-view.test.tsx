// D-3 test-first (task brief): the abs-page link + "open on arXiv" button
// are ALWAYS present in the header — pending, loaded, or errored — per §6b
// link-back. Child regions (arxiv-pdf-frame.tsx, cited-excerpts-pane.tsx)
// are mocked out: their own behavior is covered by their own test files;
// this file is about the split-view's layout/header contract and the
// #29 wiring gap (citationsByPaper -> the detail hook's chunk ids).
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaperSplitView } from "@/components/viewer/paper-split-view";
import { useViewerStore } from "@/stores/viewer-store";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useViewerPaper } from "@/hooks/use-viewer-paper";

vi.mock("@/hooks/use-viewer-paper");
vi.mock("@/components/viewer/arxiv-pdf-frame", () => ({
  ArxivPdfFrame: ({ arxivId, version }: { arxivId: string; version: string | null }) => (
    <div data-testid="pdf-frame">
      {arxivId}/{version ?? "unpinned"}
    </div>
  ),
}));
vi.mock("@/components/viewer/cited-excerpts-pane", () => ({
  CitedExcerptsPane: () => <div data-testid="excerpts-pane" />,
}));

const useViewerPaperMock = vi.mocked(useViewerPaper);

function mockDetail(overrides: Partial<ReturnType<typeof useViewerPaper>> = {}) {
  useViewerPaperMock.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    ...overrides,
  } as ReturnType<typeof useViewerPaper>);
}

beforeEach(() => {
  useViewerStore.getState().reset();
  useAgentSessionStore.getState().reset();
  useViewerPaperMock.mockReset();
});

describe("PaperSplitView", () => {
  it("renders nothing when no paper is open", () => {
    mockDetail();
    const { container } = render(<PaperSplitView />);
    expect(container).toBeEmptyDOMElement();
  });

  it("always shows the abs-page link and an open-on-arXiv button while the detail fetch is pending", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail({ isPending: true });
    render(<PaperSplitView />);

    const links = screen.getAllByRole("link", { name: /open on arXiv|abs page/i });
    expect(links.length).toBeGreaterThanOrEqual(2);
    links.forEach((link) =>
      expect(link).toHaveAttribute("href", "https://arxiv.org/abs/1409.7842"),
    );
  });

  it("always shows the abs-page link and open-on-arXiv button even if the paper detail 404s", () => {
    useViewerStore.getState().setPaper("9999.99999");
    mockDetail({ isError: true });
    render(<PaperSplitView />);

    const links = screen.getAllByRole("link", { name: /open on arXiv|abs page/i });
    links.forEach((link) =>
      expect(link).toHaveAttribute("href", "https://arxiv.org/abs/9999.99999"),
    );
  });

  it("shows the pinned version once the detail loads", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail({
      data: {
        title: "A complete KALDI recipe",
        authors: "A. Ali",
        primary_category: "cs.CL",
        year: 2014,
        version: "v3",
        excerpts: [],
        excerpts_truncated: false,
        indexed: true,
      },
    });
    render(<PaperSplitView />);
    expect(screen.getByText("version 3")).toBeInTheDocument();
  });

  it('says "latest version" when version is NULL (D9 fallback)', () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail({
      data: {
        title: "t",
        authors: "a",
        primary_category: "cs.CL",
        year: 2014,
        version: null,
        excerpts: [],
        excerpts_truncated: false,
        indexed: true,
      },
    });
    render(<PaperSplitView />);
    expect(screen.getByText("latest version")).toBeInTheDocument();
  });

  it("the back button closes the viewer by clearing viewer-store's paper", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail();
    render(<PaperSplitView />);

    screen.getByRole("button", { name: /corpus/i }).click();
    expect(useViewerStore.getState().paper).toBeNull();
  });

  it("passes the session's captured chunk_ids for the open paper to the detail hook (#29 wiring gap)", () => {
    useViewerStore.getState().setPaper("1409.7842");
    useAgentSessionStore.setState({
      citationsByPaper: new Map([["1409.7842", ["c1", "c2"]]]),
    });
    mockDetail();
    render(<PaperSplitView />);

    expect(useViewerPaperMock).toHaveBeenCalledWith("1409.7842", ["c1", "c2"]);
  });
});

// The split keys on the viewer's OWN width (`@container` + `@3xl:`), not the
// viewport's: with the agent panel docked, a 1040px window leaves this region
// 620px, and a viewport breakpoint gave the PDF 300px beside a 320px pane of
// "no excerpts yet".
describe("PaperSplitView layout", () => {
  it("lays out the PDF|excerpts split by its own width, not the viewport", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail({ isPending: true });
    const { container } = render(<PaperSplitView />);

    expect(container.firstElementChild?.className).toMatch(/@container/);
    const disclosure = screen.getByRole("button", { name: /cited excerpts/i });
    expect(disclosure.className).toMatch(/@3xl:hidden/);
    expect(disclosure.className).not.toMatch(/\bmd:/);
  });
});
