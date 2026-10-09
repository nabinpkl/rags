// The dashboard's reading surface. Its one non-obvious contract is that the
// PDF frame waits for the version: `arxiv-pdf-frame.tsx` keys its own reload
// on `<id><version>`, so mounting it before metadata lands fetches the latest
// PDF and then fetches the pinned one over the top of it (§6b wants the
// pinned one, and the reader pays for both).
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { PaperReaderPanel } from "@/components/landing/paper-reader-panel";
import { useViewerPaper } from "@/hooks/use-viewer-paper";

vi.mock("@/hooks/use-viewer-paper");
vi.mock("@/components/viewer/arxiv-pdf-frame", () => ({
  ArxivPdfFrame: ({ arxivId, version }: { arxivId: string; version: string | null }) => (
    <div data-testid="pdf-frame">
      {arxivId}/{version ?? "unpinned"}
    </div>
  ),
}));

const useViewerPaperMock = vi.mocked(useViewerPaper);

function mockPaper(overrides: Partial<ReturnType<typeof useViewerPaper>> = {}) {
  useViewerPaperMock.mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    ...overrides,
  } as ReturnType<typeof useViewerPaper>);
}

const VGG = {
  title: "Very Deep Convolutional Networks",
  authors: "Karen Simonyan, Andrew Zisserman",
  year: 2014,
  primary_category: "cs.CV",
  version: "v6",
  excerpts: [],
  excerpts_truncated: false,
  indexed: false,
};

beforeEach(() => useViewerPaperMock.mockReset());

describe("PaperReaderPanel", () => {
  it("opens the PDF pinned to the version the catalog knows", () => {
    mockPaper({ data: VGG });

    render(<PaperReaderPanel arxivId="1409.1556" />);

    expect(screen.getByTestId("pdf-frame")).toHaveTextContent("1409.1556/v6");
    expect(screen.getByText("Very Deep Convolutional Networks")).toBeInTheDocument();
    expect(screen.getByText("version 6")).toBeInTheDocument();
  });

  it("holds the PDF back until the version is known", () => {
    mockPaper({ isPending: true });

    render(<PaperReaderPanel arxivId="1409.1556" />);

    expect(screen.queryByTestId("pdf-frame")).not.toBeInTheDocument();
  });

  it("links back to arXiv before the metadata lands (§6b)", () => {
    mockPaper({ isPending: true });

    render(<PaperReaderPanel arxivId="1409.1556" />);

    // Unpinned here, because the id alone is all we have: D9 documents that
    // fallback, and a missing link-back is not an option either way.
    for (const name of [/abs page/, /open on arXiv/]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "href",
        "https://arxiv.org/abs/1409.1556",
      );
    }
  });

  it("version-pins the link-back once the catalog answers", () => {
    mockPaper({ data: VGG });

    render(<PaperReaderPanel arxivId="1409.1556" />);

    expect(screen.getByRole("link", { name: /open on arXiv/ })).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/1409.1556v6",
    );
  });

  it("says so when neither the corpus nor the citation graph knows the id", () => {
    mockPaper({ isError: true });

    render(<PaperReaderPanel arxivId="9999.99999" />);

    expect(screen.getByText(/We hold no record of arXiv:9999.99999/)).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-frame")).not.toBeInTheDocument();
  });
});
