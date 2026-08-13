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

// What `getDocument()` itself returns (a `PDFDocumentLoadingTask`) — the
// resolved doc (`fakePdfDoc`, above) has no `destroy()` of its own; the
// loading task does, and that's what arxiv-pdf-frame.tsx's unmount cleanup
// calls (destroy() aborts network requests + the worker, per pdf.js's own
// docs — the resolved PDFDocumentProxy has no equivalent method).
function fakeLoadingTask(numPages = 3) {
  return { promise: fakePdfDoc(numPages), destroy: vi.fn().mockResolvedValue(undefined) };
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
    getDocumentMock.mockReturnValue({ promise: new Promise(() => {}), destroy: vi.fn() }); // never resolves — asserts the request itself
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    await waitFor(() => {
      expect(getDocumentMock).toHaveBeenCalledWith({ url: "https://arxiv.org/pdf/1409.7842v3" });
    });
    // The built-in reader is what rung 2 IS; the toggle offering the
    // browser viewer is how that shows in the UI now.
    expect(screen.getByRole("button", { name: /use browser viewer/i })).toBeInTheDocument();
  });
});

describe("ArxivPdfFrame — automatic fallback to rung 3", () => {
  it("drops to the excerpts-only + open-on-arXiv rung when PDF.js's own fetch fails", async () => {
    getDocumentMock.mockReturnValue({
      promise: Promise.reject(new Error("network error")),
      destroy: vi.fn(),
    });
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    const link = await screen.findByRole("link", { name: /open on arXiv/i });
    expect(link).toHaveAttribute("href", "https://arxiv.org/abs/1409.7842");
  });
});

describe("ArxivPdfFrame — manual rung toggle (rung 1, iframe)", () => {
  it("uses the SAME version-pinned arxiv.org URL as the iframe src — never our server", async () => {
    getDocumentMock.mockReturnValue(fakeLoadingTask());
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={null} />);

    await waitFor(() => expect(getDocumentMock).toHaveBeenCalled());
    screen.getByRole("button", { name: /use browser viewer/i }).click();

    const iframe = await screen.findByTitle("Paper PDF, served by arxiv.org");
    expect(iframe.getAttribute("src")).toMatch(/^https:\/\/arxiv\.org\/pdf\/1409\.7842v3/);
  });

  it("appends a #page= fragment when a page target is set", async () => {
    getDocumentMock.mockReturnValue(fakeLoadingTask());
    render(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={5} />);

    await waitFor(() => expect(getDocumentMock).toHaveBeenCalled());
    screen.getByRole("button", { name: /use browser viewer/i }).click();

    const iframe = await screen.findByTitle("Paper PDF, served by arxiv.org");
    expect(iframe.getAttribute("src")).toBe("https://arxiv.org/pdf/1409.7842v3#page=5");
  });
});

describe("ArxivPdfFrame — unmount teardown", () => {
  it("disconnects the IntersectionObserver and destroys the pdf.js loading task on unmount, not on an in-mount page-only rerun", async () => {
    const loadingTask = fakeLoadingTask();
    getDocumentMock.mockReturnValue(loadingTask);
    const disconnectSpy = vi.spyOn(IntersectionObserver.prototype, "disconnect");

    const { rerender, unmount } = render(
      <ArxivPdfFrame arxivId="1409.7842" version="v3" page={1} />,
    );
    await waitFor(() => expect(getDocumentMock).toHaveBeenCalledTimes(1));

    // A same-paper page change re-runs the load effect but must reuse the
    // already-fetched doc — not re-fetch, and not tear it down.
    rerender(<ArxivPdfFrame arxivId="1409.7842" version="v3" page={2} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Previous page").nextSibling).toHaveTextContent("p.2 / 3"),
    );
    expect(getDocumentMock).toHaveBeenCalledTimes(1);
    expect(loadingTask.destroy).not.toHaveBeenCalled();

    unmount();
    expect(disconnectSpy).toHaveBeenCalled();
    expect(loadingTask.destroy).toHaveBeenCalledTimes(1);
  });
});
