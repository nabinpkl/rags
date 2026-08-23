"use client";

import { useState } from "react";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useViewerStore } from "@/stores/viewer-store";
import { usePaperDetail } from "@/hooks/use-paper-detail";
import { ArxivPdfFrame } from "@/components/viewer/arxiv-pdf-frame";
import { CitedExcerptsPane } from "@/components/viewer/cited-excerpts-pane";
import { cn } from "@/lib/utils";

const EMPTY_CHUNK_IDS: readonly string[] = [];

/** Layout + header for the #29 viewer region: `arxiv-pdf-frame.tsx` (reading
 * surface) | `cited-excerpts-pane.tsx` (what the agent cited), under a
 * header that D-3 (DECISIONS.md) requires ALWAYS show the abs-page link and
 * an "open on arXiv" button (§6b link-back) — regardless of which D9 rung
 * the PDF pane is on, even mid-load or on a 404. Mounted by `app/page.tsx`
 * only when `viewer-store`'s `paper` is set; reads that store plus
 * `agent-session-store`'s citation capture (#29 wiring gap) directly, no
 * props — mirrors `explorer-panel.tsx`/`chat-panel.tsx`'s region-composition
 * role. */
export function PaperSplitView() {
  const paper = useViewerStore((state) => state.paper);
  const page = useViewerStore((state) => state.page);
  const setPaper = useViewerStore((state) => state.setPaper);
  const setPage = useViewerStore((state) => state.setPage);
  const chunkIds = useAgentSessionStore((state) =>
    paper ? (state.citationsByPaper.get(paper) ?? EMPTY_CHUNK_IDS) : EMPTY_CHUNK_IDS,
  );

  const { data, isPending, isError } = usePaperDetail(paper, chunkIds);
  // Stacked layout only (the region narrower than `@3xl`): the pane is a
  // bottom disclosure there, collapsed by default so the PDF — the reading
  // surface (D9) — keeps the screen. Side by side, it is the docked right
  // column and this flag does nothing.
  const [excerptsOpen, setExcerptsOpen] = useState(false);

  if (!paper) return null;

  const absUrl = `https://arxiv.org/abs/${paper}`;
  const excerptCount = data?.excerpts?.length ?? 0;

  return (
    // `@container`: the PDF|excerpts split keys on THIS region's width
    // (`@3xl:` = 768px of it), not the viewport's — with the agent panel
    // docked, a 1040px window leaves the viewer 620px, and a viewport
    // breakpoint gave the reading surface 300px beside a 320px pane of
    // "no excerpts yet".
    <div className="@container bg-paper flex h-full min-w-0 flex-col">
      <div className="border-line bg-panel border-b px-3 py-2.5 sm:px-5 sm:py-3">
        <div className="mb-1.5 flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setPaper(null)}
            className="text-muted hover:text-ink -ml-2 flex h-9 items-center px-2 font-mono text-[11px]"
          >
            ← corpus
          </button>
          <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 font-mono text-[10.5px]">
            {/* §6b pins the PDF to a version; what a reader needs from that is
                WHICH version they're reading, not the word "pinned". */}
            {data?.version ? `version ${data.version.replace(/^v/, "")}` : "latest version"}
          </span>
        </div>
        <h2 className="text-ink font-serif text-[18px] leading-tight font-semibold">
          {isPending ? "Loading…" : isError ? `Paper ${paper}` : data?.title}
        </h2>
        {/* Clamped: on a phone the header is what the PDF has to fit under,
            and a full affiliation list pushed the first page below the
            fold. The full string is a hover away. */}
        {data && (
          <p className="text-muted line-clamp-1 text-[12px] sm:line-clamp-2" title={data.authors}>
            {data.authors}
          </p>
        )}
        <div className="text-muted flex flex-wrap items-center gap-x-1.5 text-[12px]">
          {data && (
            <>
              <span>{data.year}</span>
              <span>·</span>
              <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 font-mono text-[10.5px]">
                {data.primary_category}
              </span>
              <span>·</span>
            </>
          )}
          {/* §6b: the abs-page link + "open on arXiv" CTA are ALWAYS present
              (D-3) — even before paper-detail resolves or if it 404s, since
              `paper` (the arxiv id) alone is enough to build both URLs. */}
          <a
            href={absUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-teal-ink hover:underline"
          >
            abs page ↗
          </a>
          <a
            href={absUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="border-teal-ink text-teal-ink hover:bg-teal-soft ml-1 rounded border px-2 py-0.5 font-mono text-[10.5px]"
          >
            open on arXiv ↗
          </a>
        </div>
      </div>

      {/* h-full (not just flex-1): a CSS grid's implicit row auto-sizes to
          its tallest item's content by default, which would let the PDF
          pane's many stacked pages grow the row (and the whole document)
          instead of scrolling internally — h-full pins the row to the
          flex parent's remaining height so each grid item's own
          overflow-auto region is what scrolls. */}
      {/* Narrower than `@3xl` this is two ROWS — the PDF taking 1fr and the
          excerpts collapsing to their header — because a 50/50 split on a
          phone gives the reading surface half a screen, usually to show "no
          cited excerpts yet". */}
      <div className="grid h-full min-h-0 flex-1 grid-cols-1 grid-rows-[1fr_auto] @3xl:grid-cols-[1fr_320px] @3xl:grid-rows-1">
        {isPending ? (
          <div className="text-machine-text flex h-full items-center justify-center bg-[#3c4650] font-mono text-[11px]">
            loading…
          </div>
        ) : isError ? (
          <div className="text-machine-text flex h-full items-center justify-center bg-[#3c4650] p-6 text-center font-mono text-[11px]">
            Couldn&apos;t load this paper. It may not be in the corpus.
          </div>
        ) : (
          // `key={paper}`: a fresh mount per paper resets ALL local rung/scroll
          // state (arxiv-pdf-frame.tsx) cleanly — a fallback chosen for one
          // paper must not stick to the next. Simpler and lint-clean versus an
          // effect that calls setState synchronously on `idv` change.
          <ArxivPdfFrame key={paper} arxivId={paper} version={data?.version ?? null} page={page} />
        )}
        {/* ONE pane instance in both layouts: it mints DOM ids per chunk for
            its section jump-links, and a second copy would make
            getElementById pick whichever rendered first. */}
        <section className="border-line bg-panel flex min-h-0 flex-col border-t @3xl:border-t-0 @3xl:border-l">
          <button
            type="button"
            onClick={() => setExcerptsOpen((open) => !open)}
            aria-expanded={excerptsOpen}
            className="text-muted hover:text-ink flex h-11 shrink-0 items-center gap-2 px-3.5 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase @3xl:hidden"
          >
            Cited excerpts
            {excerptCount > 0 && (
              <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 text-[10.5px]">
                {excerptCount}
              </span>
            )}
            <span aria-hidden="true" className="ml-auto">
              {excerptsOpen ? "▾" : "▴"}
            </span>
          </button>
          <div
            className={cn(
              // Expanded, THIS box scrolls: its height is content-driven up to
              // the cap, so the pane's own `h-full` has no definite parent to
              // resolve against and its overflow would never trigger. Docked,
              // the row has a real height and the pane scrolls itself.
              "min-h-0 flex-1 overflow-y-auto @3xl:block @3xl:max-h-none @3xl:overflow-visible",
              excerptsOpen ? "max-h-[45vh]" : "hidden @3xl:block",
            )}
          >
            <CitedExcerptsPane
              excerpts={data?.excerpts ?? []}
              excerptsTruncated={data?.excerpts_truncated ?? false}
              onJumpToPage={(target) => setPage(target)}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
