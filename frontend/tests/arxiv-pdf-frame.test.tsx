// D9/§6b test-first (task brief): every PDF byte the app ever touches comes
// from the user's own browser fetching arxiv.org DIRECTLY, version-pinned,
// never our own server. `pdfjs-dist` is mocked wholesale — real PDF
// rendering needs a network fetch and a canvas backend jsdom doesn't have;
// what's under test here is the URL this component hands it and the rung
// ladder's fallback behavior, not pdf.js's own rendering.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ArxivPdfFrame, arxivPdfUrl } from "@/components/viewer/arxiv-pdf-frame";

const { getDocumentMock } = vi.hoisted(() => ({ getDocumentMock: vi.fn() }));

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: getDocumentMock,
}));

function fakePdfDoc(numPages = 3) {
  return {
    numPages,
    getPage: vi.fn().mockResolvedValue({
      getViewport: vi.fn().mockReturnValue({ width: 600, height: 800 }),
      render: vi.fn().mockReturnValue({ promise: Promise.resolve() }),
    }),
  };
}

beforeEach(() => {
  getDocumentMock.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("arxivPdfUrl — §6b version pinning", () => {
  it("pins to the exact version when one is known", () => {
    expect(arxivPdfUrl("2401.00001", "v3")).toBe("https://arxiv.org/pdf/2401.00001v3");
  });

  it("falls back to the unpinned URL when version is NULL (pre-backfill stragglers, D9)", () => {
    expect(arxivPdfUrl("2401.00001", null)).toBe("https://arxiv.org/pdf/2401.00001");
  });
});

describe("ArxivPdfFrame — rung 2 (PDF.js) is the default and fetches arxiv.org directly", () => {
  it("requests the version-pinned URL, never a same-origin/proxy path", async () => {
    getDocumentMock.mockReturnValue({ promise: new Promise(() => {}) }); // never resolves — asserts the request itself
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    await waitFor(() => {
      expect(getDocumentMock).toHaveBeenCalledWith({ url: "https://arxiv.org/pdf/1409.7842v3" });
    });
    expect(screen.getByText(/rung 2/)).toBeInTheDocument();
  });
});

describe("ArxivPdfFrame — automatic fallback to rung 3", () => {
  it("drops to the excerpts-only + open-on-arXiv rung when PDF.js's own fetch fails", async () => {
    getDocumentMock.mockReturnValue({ promise: Promise.reject(new Error("network error")) });
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    const link = await screen.findByRole("link", { name: /open on arXiv/i });
    expect(link).toHaveAttribute("href", "https://arxiv.org/abs/1409.7842");
  });
});

describe("ArxivPdfFrame — manual rung toggle (rung 1, iframe)", () => {
  it("uses the SAME version-pinned arxiv.org URL as the iframe src — never our server", async () => {
    getDocumentMock.mockReturnValue({ promise: fakePdfDoc() });
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    await waitFor(() => expect(getDocumentMock).toHaveBeenCalled());
    screen.getByRole("button", { name: /rung 2/ }).click();

    const iframe = await screen.findByTitle("Paper PDF, served by arxiv.org");
    expect(iframe.getAttribute("src")).toMatch(/^https:\/\/arxiv\.org\/pdf\/1409\.7842v3/);
  });

  it("appends a #page= fragment when a page target is set", async () => {
    getDocumentMock.mockReturnValue({ promise: fakePdfDoc() });
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={5} />);

    await waitFor(() => expect(getDocumentMock).toHaveBeenCalled());
    screen.getByRole("button", { name: /rung 2/ }).click();

    const iframe = await screen.findByTitle("Paper PDF, served by arxiv.org");
    expect(iframe.getAttribute("src")).toBe("https://arxiv.org/pdf/1409.7842v3#page=5");
  });
});
