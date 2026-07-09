import "@testing-library/jest-dom/vitest";

// jsdom has no IntersectionObserver — used by
// components/viewer/arxiv-pdf-frame.tsx for PDF.js's lazy per-page render.
// A no-op stub is enough: tests that exercise rung 2 mock `pdfjs-dist`
// itself (see tests/arxiv-pdf-frame.test.tsx), so no observer callback ever
// needs to actually fire.
class IntersectionObserverStub {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: readonly number[] = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
globalThis.IntersectionObserver ??=
  IntersectionObserverStub as unknown as typeof IntersectionObserver;
