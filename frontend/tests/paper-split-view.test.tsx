// D-3 test-first (task brief): the abs-page link + "open on arXiv" button
// are ALWAYS present in the header — pending, loaded, or errored — per §6b
// link-back. Child regions (arxiv-pdf-frame.tsx, cited-excerpts-pane.tsx)
// are mocked out: their own behavior is covered by their own test files;
// this file is about the split-view's layout/header contract and the
// #29 wiring gap (citationsByPaper -> usePaperDetail's chunk ids).
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaperSplitView } from "@/components/viewer/paper-split-view";
import { useViewerStore } from "@/stores/viewer-store";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { usePaperDetail } from "@/hooks/use-paper-detail";

vi.mock("@/hooks/use-paper-detail");
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

const usePaperDetailMock = vi.mocked(usePaperDetail);

function mockDetail(overrides: Partial<ReturnType<typeof usePaperDetail>> = {}) {
  usePaperDetailMock.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    ...overrides,
  } as ReturnType<typeof usePaperDetail>);
}

beforeEach(() => {
  useViewerStore.getState().reset();
  useAgentSessionStore.getState().reset();
  usePaperDetailMock.mockReset();
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
        arxiv_id: "1409.7842",
        title: "A complete KALDI recipe",
        authors: "A. Ali",
        abstract: "",
        categories: "cs.CL",
        primary_category: "cs.CL",
        year: 2014,
        published: "2014-01-01",
        venue: null,
        license: null,
        version: "v3",
        facets: {},
        n_chunks: 10,
        excerpts: [],
        excerpts_truncated: false,
      },
    });
    render(<PaperSplitView />);
    expect(screen.getByText("pinned v3")).toBeInTheDocument();
  });

  it("shows 'unpinned' when version is NULL (D9 fallback)", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail({
      data: {
        arxiv_id: "1409.7842",
        title: "t",
        authors: "a",
        abstract: "",
        categories: "cs.CL",
        primary_category: "cs.CL",
        year: 2014,
        published: "2014-01-01",
        venue: null,
        license: null,
        version: null,
        facets: {},
        n_chunks: 1,
        excerpts: [],
        excerpts_truncated: false,
      },
    });
    render(<PaperSplitView />);
    expect(screen.getByText("unpinned")).toBeInTheDocument();
  });

  it("the back button closes the viewer by clearing viewer-store's paper", () => {
    useViewerStore.getState().setPaper("1409.7842");
    mockDetail();
    render(<PaperSplitView />);

    screen.getByRole("button", { name: /corpus/i }).click();
    expect(useViewerStore.getState().paper).toBeNull();
  });

  it("passes the session's captured chunk_ids for the open paper to usePaperDetail (#29 wiring gap)", () => {
    useViewerStore.getState().setPaper("1409.7842");
    useAgentSessionStore.setState({
      citationsByPaper: new Map([["1409.7842", ["c1", "c2"]]]),
    });
    mockDetail();
    render(<PaperSplitView />);

    expect(usePaperDetailMock).toHaveBeenCalledWith("1409.7842", ["c1", "c2"]);
  });
});
