"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";
import { cn } from "@/lib/utils";

// D9's fallback ladder, isolated to this one file — the named seam spec §4d
// calls out ("`arxiv-pdf-frame.tsx` isolates the D9 fallback ladder"), so a
// future rung change (or a real Safari/WebKit failure — spec §10, unverified
// here) is a swap inside this file, nothing else. D-2 (DECISIONS.md):
// inverted from D9's original iframe-first draft — an embedded webview with
// no native PDF plugin turns an iframe PDF load into a download (observed
// 2026-07-04), so rung 2 (PDF.js fetching bytes itself, in the user's
// browser) is the default; rung 1 (iframe) is a manual fallback/comparison;
// rung 3 (excerpts-only + "open on arXiv") is automatic once PDF.js's own
// fetch fails — there is nothing else to try client-side. §6b/§6c: every
// byte crosses arxiv.org -> the user's browser directly; this file never
// fetches, proxies, or caches PDF bytes through our own server.
type Rung = 1 | 2 | 3;

const DEFAULT_RUNG: Rung = 2;
const PAGE_WIDTH_SCALE_CAP = 1.6; // mirrors docs/mockup.html's cssW cap
const PAGE_MARGIN_PX = 32;
const LAZY_RENDER_MARGIN = "600px 0px"; // how far outside the viewport a page pre-renders

// pdfjs-dist touches browser-only globals (DOMMatrix et al.) at module
// EVALUATION time, not just at call time — a static top-level import breaks
// Next's static-export prerender, which evaluates every client component's
// module server-side once to produce the initial HTML (D13). A dynamic
// import, run only from inside the client-only effect below, defers that
// evaluation to the real browser and is cached after the first paper opens.
let pdfjsModulePromise: Promise<typeof import("pdfjs-dist")> | null = null;

function loadPdfjs() {
  pdfjsModulePromise ??= import("pdfjs-dist").then((pdfjsLib) => {
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      "pdfjs-dist/build/pdf.worker.min.mjs",
      import.meta.url,
    ).toString();
    return pdfjsLib;
  });
  return pdfjsModulePromise;
}

/** D9/§6b: version-pinned whenever we have one (`version` from the detail
 * endpoint, e.g. "v3"); NULL falls back to the unpinned URL — never any
 * origin but arxiv.org, never our own server. */
export function arxivPdfUrl(arxivId: string, version: string | null): string {
  return `https://arxiv.org/pdf/${arxivId}${version ?? ""}`;
}

interface ArxivPdfFrameProps {
  arxivId: string;
  version: string | null;
  /** The citation-driven page jump target (viewer-store's `page`, written
   * only by cited-excerpts-pane.tsx's anchors). Free scrolling/prev-next
   * inside this component stays local state, per the task brief — not
   * shareable/URL state, so it never writes back here. */
  page: number | null;
}

/** Renders exactly what pdf.js reports: current page (best-effort) / total —
 * `#page=N` precision "is enhancement, not correctness" (D9). */
export function ArxivPdfFrame({ arxivId, version, page }: ArxivPdfFrameProps) {
  const idv = `${arxivId}${version ?? ""}`;
  const url = arxivPdfUrl(arxivId, version);
  const absUrl = `https://arxiv.org/abs/${arxivId}`;
  const targetPage = page ?? 1;

  const [rung, setRung] = useState<Rung>(DEFAULT_RUNG);
  const [loading, setLoading] = useState(false);
  const [displayPage, setDisplayPage] = useState(1);
  const [numPages, setNumPages] = useState(1);

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const pagesRef = useRef<HTMLDivElement | null>(null);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  // The loading task (not the resolved doc) is what actually owns the
  // in-flight network requests + the pdf.js worker — `PDFDocumentProxy` has
  // no `destroy()` of its own; `PDFDocumentLoadingTask.destroy()` is the
  // real teardown ("abort all network requests and destroy the worker").
  const loadingTaskRef = useRef<PDFDocumentLoadingTask | null>(null);
  const loadedIdvRef = useRef<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const numPagesRef = useRef(1);
  const previousIdvRef = useRef<string | null>(null);

  const gotoPage = useCallback((n: number, instant: boolean) => {
    const clamped = Math.min(Math.max(1, n), numPagesRef.current);
    const div = pagesRef.current?.querySelector<HTMLDivElement>(`[data-page="${clamped}"]`);
    if (div) {
      div.scrollIntoView({ block: "start", behavior: instant ? "auto" : "smooth" });
      div.classList.remove("jumpflash");
      void div.offsetWidth; // restart the CSS animation on repeat jumps to the same page
      div.classList.add("jumpflash");
    }
    setDisplayPage(clamped);
  }, []);

  // Rung 2: fetch (browser -> arxiv.org directly) + continuous-scroll render
  // with lazy per-page canvases. Re-runs on every targetPage change too, but
  // ensureDoc/buildPagePlaceholders below are no-ops once idv is already
  // loaded, so a same-paper page jump only ever calls gotoPage.
  useEffect(() => {
    if (rung !== 2) return;
    const wrap = wrapRef.current;
    const pages = pagesRef.current;
    if (!wrap || !pages) return;

    let cancelled = false;

    // wrap/pages passed explicitly (not closed over) so every helper below
    // has a non-null-typed element regardless of what TS can prove about a
    // captured outer const inside a nested async function.
    async function renderPageInto(
      div: HTMLDivElement,
      doc: PDFDocumentProxy,
      wrapEl: HTMLDivElement,
    ) {
      if (div.dataset.rendered) return;
      div.dataset.rendered = "1";
      const pdfPage = await doc.getPage(Number(div.dataset.page));
      const dpr = window.devicePixelRatio || 1;
      const base = pdfPage.getViewport({ scale: 1 });
      const cssWidth = Math.min(
        wrapEl.clientWidth - PAGE_MARGIN_PX,
        base.width * PAGE_WIDTH_SCALE_CAP,
      );
      const viewport = pdfPage.getViewport({ scale: (cssWidth / base.width) * dpr });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      div.style.width = `${cssWidth}px`;
      div.style.height = "auto";
      div.appendChild(canvas);
      await pdfPage.render({ canvas, viewport }).promise;
    }

    async function ensureDoc(): Promise<PDFDocumentProxy> {
      if (loadedIdvRef.current === idv && docRef.current) return docRef.current;
      setLoading(true);
      const pdfjsLib = await loadPdfjs();
      const loadingTask = pdfjsLib.getDocument({ url });
      loadingTaskRef.current = loadingTask;
      const doc = await loadingTask.promise;
      docRef.current = doc;
      loadedIdvRef.current = idv;
      numPagesRef.current = doc.numPages;
      setNumPages(doc.numPages);
      return doc;
    }

    async function buildPagePlaceholders(
      doc: PDFDocumentProxy,
      wrapEl: HTMLDivElement,
      pagesEl: HTMLDivElement,
    ) {
      if (pagesEl.dataset.idv === idv) return; // already built for this paper
      pagesEl.dataset.idv = idv;
      pagesEl.replaceChildren();
      observerRef.current?.disconnect();

      const first = await doc.getPage(1);
      const base = first.getViewport({ scale: 1 });
      const cssWidth = Math.min(
        wrapEl.clientWidth - PAGE_MARGIN_PX,
        base.width * PAGE_WIDTH_SCALE_CAP,
      );
      const cssHeight = (cssWidth * base.height) / base.width;

      for (let n = 1; n <= doc.numPages; n += 1) {
        const div = document.createElement("div");
        div.className = "pdf-page";
        div.dataset.page = String(n);
        div.style.width = `${cssWidth}px`;
        div.style.height = `${cssHeight}px`;
        pagesEl.appendChild(div);
      }

      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting)
              void renderPageInto(entry.target as HTMLDivElement, doc, wrapEl);
          });
        },
        { root: wrapEl, rootMargin: LAZY_RENDER_MARGIN },
      );
      pagesEl
        .querySelectorAll<HTMLDivElement>("[data-page]")
        .forEach((div) => observer.observe(div));
      observerRef.current = observer;
    }

    ensureDoc()
      .then(async (doc) => {
        if (cancelled) return;
        await buildPagePlaceholders(doc, wrap, pages);
        if (cancelled) return;
        setLoading(false);
        const instant = previousIdvRef.current !== idv;
        previousIdvRef.current = idv;
        gotoPage(targetPage, instant);
      })
      .catch(() => {
        if (cancelled) return;
        setLoading(false);
        setRung(3); // automatic: nothing else to try client-side (D9)
      });

    return () => {
      cancelled = true;
    };
  }, [rung, idv, url, targetPage, gotoPage]);

  // Real teardown, once per mount — deliberately NOT in the effect above.
  // That effect's cleanup runs on every dependency change (rung/targetPage),
  // not just unmount, but `idv` is constant for the lifetime of one mounted
  // instance (paper-split-view.tsx only ever changes it via `key={paper}`,
  // i.e. a full remount) — ensureDoc/buildPagePlaceholders already
  // short-circuit reuse of the SAME doc/observer across those in-mount
  // re-runs, so destroying them there would break that reuse. Reading refs
  // at cleanup time (not closing over a value) means this always tears down
  // whatever the effect above most recently built, however many times it
  // re-ran, exactly once when this component actually goes away.
  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
      void loadingTaskRef.current?.destroy();
    };
  }, []);

  // Keeps the page label honest while the user scrolls freely (rung 2 only).
  useEffect(() => {
    if (rung !== 2) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    function onScroll() {
      const wrapEl = wrapRef.current;
      if (!wrapEl) return;
      const wrapTop = wrapEl.getBoundingClientRect().top;
      let best = 1;
      let bestDist = Number.POSITIVE_INFINITY;
      wrapEl.querySelectorAll<HTMLDivElement>("[data-page]").forEach((div) => {
        const dist = Math.abs(div.getBoundingClientRect().top - wrapTop - 44);
        if (dist < bestDist) {
          bestDist = dist;
          best = Number(div.dataset.page);
        }
      });
      setDisplayPage((current) => (current === best ? current : best));
    }
    wrap.addEventListener("scroll", onScroll, { passive: true });
    return () => wrap.removeEventListener("scroll", onScroll);
  }, [rung, idv]);

  const toggleRung = () => setRung((current) => (current === 2 ? 1 : 2));

  return (
    // `min-w-0`: as a grid item this box's automatic minimum size is its
    // min-content, which the rendered pages set — and those pages are sized
    // FROM this box's clientWidth (renderPageInto), so an oversized column
    // keeps the pages oversized and the pages keep the column oversized. That
    // loop pushed the excerpts pane past the viewport and put a horizontal
    // scrollbar on the whole page; the pane is scrollable, so it is free to
    // shrink below its content.
    <div className="relative flex h-full min-h-0 min-w-0 flex-col bg-[#3c4650]">
      {/* Bounded on BOTH sides and allowed to wrap: unbounded, the provenance
          line and the rung button ran off a 390px screen and collided with
          the scrollbar. */}
      <div className="text-machine-text absolute top-2.5 right-2.5 left-2.5 z-10 flex flex-wrap items-center gap-x-2 gap-y-1 rounded bg-black/60 px-2.5 py-1 font-mono text-[10.5px]">
        <span>
          arxiv.org/pdf/<b className="text-teal">{idv}</b>
          {rung === 2 && !loading ? ` p.${displayPage}` : ""}
        </span>
        {/* Provenance, kept in plain words: the point a reader cares about is
            that the file comes from arXiv itself, not that we don't proxy it
            (§6b, which is our constraint to keep, not their vocabulary). */}
        <span>— loaded straight from arXiv</span>
        <button
          type="button"
          onClick={toggleRung}
          title="Switch how this PDF is displayed"
          className="border-machine-line text-machine-muted hover:border-teal hover:text-teal rounded border px-1.5 py-0.5 font-mono text-[9.5px]"
        >
          {/* Names the ACTION, not the current rung: a label reading "reader
              view" next to a reader view can't be told from a status. */}
          {rung === 1 ? "use built-in reader" : "use browser viewer"}
        </button>
      </div>

      {rung === 1 && (
        <iframe
          title="Paper PDF, served by arxiv.org"
          loading="lazy"
          src={`${url}${page ? `#page=${page}` : ""}`}
          className="h-full w-full border-0"
          onError={() => setRung(3)}
        />
      )}

      {rung === 2 && (
        <>
          <div
            ref={wrapRef}
            aria-label="Rendered PDF, continuous scroll"
            className="relative flex-1 overflow-auto px-2 pt-16 pb-4 sm:px-4 sm:pt-11"
            style={{ scrollBehavior: "smooth" }}
          >
            <div ref={pagesRef} />
            {loading && (
              <div className="text-machine-text absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 font-mono text-[11px]">
                loading from arxiv.org…
              </div>
            )}
          </div>
          {!loading && (
            <div className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2.5 rounded bg-black/60 px-2.5 py-1">
              <button
                type="button"
                aria-label="Previous page"
                onClick={() => gotoPage(displayPage - 1, false)}
                className="text-machine-text hover:text-teal px-1.5 text-[15px]"
              >
                ‹
              </button>
              <span className="text-machine-text font-mono text-[10.5px]">
                p.{displayPage} / {numPages}
              </span>
              <button
                type="button"
                aria-label="Next page"
                onClick={() => gotoPage(displayPage + 1, false)}
                className="text-machine-text hover:text-teal px-1.5 text-[15px]"
              >
                ›
              </button>
            </div>
          )}
        </>
      )}

      {rung === 3 && (
        <div
          className={cn(
            "text-machine-text absolute top-1/2 left-1/2 max-w-[280px] -translate-x-1/2 -translate-y-1/2",
            "rounded bg-black/70 px-4 py-3 text-center text-[12px] leading-relaxed",
          )}
        >
          Couldn&apos;t load the PDF (offline?). Read the cited excerpts, or
          <a
            href={absUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-teal hover:text-machine-text ml-1 underline"
          >
            open on arXiv ↗
          </a>
        </div>
      )}
    </div>
  );
}
