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

// jsdom implements no layout, so it ships neither `scrollIntoView` (used by
// components/landing/foundation-detail.tsx to keep a swapped panel in view)
// nor `Element.scrollTo` (used by components/viewer/arxiv-pdf-frame.tsx to
// scroll its own pane to a page). Both would throw. Nothing here asserts on
// scrolling; a no-op is the whole contract.
Element.prototype.scrollIntoView ??= function scrollIntoView() {};
Element.prototype.scrollTo ??= function scrollTo() {};

// jsdom has no ResizeObserver either — hooks/use-infinite-virtual-list.ts
// re-measures the list's offset with one. jsdom has no layout to resize, so
// an observer that never fires is exactly what it would do.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
