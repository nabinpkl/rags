"use client";

import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useViewerStore } from "@/stores/viewer-store";
import { usePaperDetail } from "@/hooks/use-paper-detail";
import { ArxivPdfFrame } from "@/components/viewer/arxiv-pdf-frame";
import { CitedExcerptsPane } from "@/components/viewer/cited-excerpts-pane";

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

  if (!paper) return null;

  const absUrl = `https://arxiv.org/abs/${paper}`;

  return (
    <div className="bg-paper flex h-full min-w-0 flex-col">
      <div className="border-line bg-panel border-b px-5 py-3">
        <div className="mb-1.5 flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setPaper(null)}
            className="text-muted font-mono text-[11px]"
          >
            ← corpus
          </button>
          <span className="bg-teal-soft text-teal-deep rounded px-1.5 py-0.5 font-mono text-[10.5px]">
            {data?.version ? `pinned ${data.version}` : "unpinned"}
          </span>
        </div>
        <h2 className="text-ink font-serif text-[18px] leading-tight font-semibold">
          {isPending ? "Loading…" : isError ? `Paper ${paper}` : data?.title}
        </h2>
        <div className="text-muted flex flex-wrap items-center gap-x-1.5 text-[12px]">
          {data && (
            <>
              <span>{data.authors}</span>
              <span>·</span>
              <span>{data.year}</span>
              <span>·</span>
              <span className="bg-teal-soft text-teal-deep rounded px-1.5 py-0.5 font-mono text-[10.5px]">
                {data.primary_category}
              </span>
              <span>·</span>
            </>
          )}
          {/* §6b: the abs-page link + "open on arXiv" CTA are ALWAYS present
              (D-3) — even before paper-detail resolves or if it 404s, since
              `paper` (the arxiv id) alone is enough to build both URLs. */}
          <a href={absUrl} target="_blank" rel="noopener noreferrer" className="text-teal-deep">
            abs page ↗
          </a>
          <a
            href={absUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="border-teal-deep text-teal-deep hover:bg-teal-soft ml-1 rounded border px-2 py-0.5 font-mono text-[10.5px]"
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
      <div className="grid h-full min-h-0 flex-1 grid-cols-1 md:grid-cols-[1fr_320px]">
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
        <CitedExcerptsPane
          excerpts={data?.excerpts ?? []}
          excerptsTruncated={data?.excerpts_truncated ?? false}
          onJumpToPage={(target) => setPage(target)}
        />
      </div>
    </div>
  );
}
