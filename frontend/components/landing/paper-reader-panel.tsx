"use client";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { ArxivPdfFrame } from "@/components/viewer/arxiv-pdf-frame";
import { useViewerPaper } from "@/hooks/use-viewer-paper";
import { arxivAbsUrl } from "@/lib/arxiv-links";

/** The paper itself, open on the dashboard beside the panels that counted it.
 *
 * Same reading surface as the app shell's viewer — `arxiv-pdf-frame.tsx`,
 * D9 rung 2: the bytes go arxiv.org -> the reader's browser, version-pinned,
 * never through us (§6b). What this leaves out is the cited-excerpts pane,
 * which mints DOM ids per chunk for its jump anchors; a second live instance
 * would make `getElementById` pick whichever mounted first, and on this page
 * the agent's citations surface in the ask panel instead.
 *
 * Metadata comes from `use-viewer-paper.ts`, so a co-cited work we hold no
 * text for opens here with a title and a version pin like any other.
 */
export function PaperReaderPanel({ arxivId }: { arxivId: string }) {
  const { data, isPending, isError } = useViewerPaper(arxivId);
  const absUrl = arxivAbsUrl(arxivId, data?.version);

  return (
    <DashboardPanel
      title={isPending ? "Loading…" : (data?.title ?? `arXiv:${arxivId}`)}
      meta={data?.version ? `version ${data.version.replace(/^v/, "")}` : "latest version"}
      bodyClassName="min-h-0 p-0"
    >
      <div className="border-line text-muted flex shrink-0 flex-wrap items-center gap-x-2.5 gap-y-1 border-b px-4 py-2 text-[11.5px]">
        {data?.authors && (
          <span className="min-w-0 flex-1 truncate" title={data.authors}>
            {data.authors}
          </span>
        )}
        {/* §6b link-back (D-3): the abs page and the "open on arXiv" button
            are present whatever the PDF pane is doing, since the id alone
            builds both URLs. */}
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
          className="border-teal-ink text-teal-ink hover:bg-teal-soft rounded border px-2 py-0.5 font-mono text-[10.5px]"
        >
          open on arXiv ↗
        </a>
      </div>

      {/* The frame mounts only once the version is known: it keys its own
          reload on `<id><version>`, so mounting it early fetches the latest
          PDF and then fetches the pinned one over the top of it. */}
      <div className="min-h-0 flex-1">
        {isPending ? (
          <div className="text-surround-text flex h-full items-center justify-center bg-surround font-mono text-[11px]">
            loading…
          </div>
        ) : isError ? (
          <div className="text-surround-text flex h-full items-center justify-center bg-surround p-6 text-center font-mono text-[11px]">
            Couldn&apos;t load this paper. We hold no record of arXiv:{arxivId}.
          </div>
        ) : (
          <ArxivPdfFrame
            key={arxivId}
            arxivId={arxivId}
            version={data?.version ?? null}
            page={null}
          />
        )}
      </div>
    </DashboardPanel>
  );
}
