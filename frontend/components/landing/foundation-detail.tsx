"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useRef, useState } from "react";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { PaperReaderPanel } from "@/components/landing/paper-reader-panel";
import { type Foundation, fetchFoundation } from "@/lib/api-client";
import { arxivAbsUrl } from "@/lib/arxiv-links";
import { cn } from "@/lib/utils";

/** Both lists' titles are the same control: press one and that paper opens
 * in the reader beside them. The open row carries `aria-current`, since
 * "which of these am I reading" is otherwise only visible in the panel. */
const TITLE_BUTTON =
  "font-serif text-teal-ink block w-full text-left text-[14.5px] hover:underline";

/** The evidence behind one number on the page, with the paper open beside it.
 *
 * Three numbers, none of them interchangeable: total_citers is every paper
 * that cites the work; scope_size is how many of those we indexed and the
 * agent therefore reads; indexed_citers is the capped list shown here. Every
 * listed one opens (D16), and stating all three is the whole reason no
 * `readable` badge is needed on the wire.
 *
 * Reading is not a second destination. The foundation is open in the reader
 * from the moment this view mounts, and clicking any paper in either list
 * swaps the reader to it — a co-cited work we hold no text for included,
 * since its PDF was always arXiv's to serve to the reader's browser (§6b)
 * and `use-viewer-paper.ts` resolves the metadata either way.
 */
export function FoundationDetail({
  foundation,
  onBack,
  onAsk,
}: {
  foundation: Foundation;
  onBack: () => void;
  onAsk: (foundation: Foundation) => void;
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["foundation", foundation.arxiv_id],
    queryFn: () => fetchFoundation(foundation.arxiv_id, { co_cited_limit: 6, citers_limit: 6 }),
  });
  const [reading, setReading] = useState(foundation.arxiv_id);
  const readerRef = useRef<HTMLDivElement>(null);

  function read(arxivId: string) {
    setReading(arxivId);
    // Stacked (narrower than `xl`) the reader sits a screen above the lists,
    // so a click there would swap a panel nobody can see. `nearest` does
    // nothing when it is already in view, and the canvas's own
    // `scroll-smooth`/`motion-reduce:scroll-auto` picks the behaviour.
    readerRef.current?.scrollIntoView({ block: "nearest" });
  }

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="border-line bg-panel text-muted hover:text-ink mb-4 flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-[11px] transition-colors motion-reduce:transition-none"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        all foundations
      </button>

      <h2 className="max-w-[34ch] text-[26px] leading-tight font-semibold">
        <button
          type="button"
          onClick={() => read(foundation.arxiv_id)}
          className="font-serif text-ink hover:text-teal-ink text-left hover:underline"
        >
          {foundation.title ?? foundation.arxiv_id}
        </button>
      </h2>
      <p className="text-muted mt-1 mb-3.5 text-[12.5px]">
        {foundation.authors ?? "authors unknown"}
        {foundation.year ? ` · ${foundation.year} · ` : " · "}
        <a
          href={arxivAbsUrl(foundation.arxiv_id, foundation.version)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal-ink underline"
        >
          arXiv:{foundation.arxiv_id}
          {foundation.version ?? ""}
        </a>
      </p>

      <p className="bg-teal-soft border-teal mb-6 border-l-[3px] px-3.5 py-2.5 text-[15px]">
        <b className="font-mono text-[17px]">{foundation.cited_by.toLocaleString()}</b> papers in
        this window cite it.
      </p>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onAsk(foundation)}
          disabled={!data?.indexed_citers.length}
          className="bg-teal-deep hover:bg-teal-deep-hover rounded px-3.5 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Ask about these papers
        </button>
        <span className="text-muted text-xs">
          {/* scope_size, NOT indexed_citers.length: the list below is capped
              for layout, the scope is every indexed paper citing this work.
              Saying "the 8 papers" here was false for every foundation. */}
          {data?.scope_size
            ? `answers come from the ${data.scope_size} papers we indexed for this claim`
            : "no indexed papers for this claim yet"}
        </span>
      </div>

      {isError && (
        <p className="text-muted mb-4 text-sm">Could not load the papers behind this number.</p>
      )}

      {/* The reader does not wait on the citation query: it needs an id, and
          the id is the foundation we already have. */}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        {/* `min-w-0`: a grid item's automatic minimum size is its min-content,
            and the PDF pane sizes its pages FROM its own clientWidth — left
            to itself that loop widened the canvas to 3841px on a 390px
            screen (arxiv-pdf-frame.tsx carries the same note). */}
        <div
          ref={readerRef}
          className="h-[58vh] min-h-[380px] min-w-0 xl:sticky xl:top-0 xl:h-[78vh]"
        >
          <PaperReaderPanel arxivId={reading} />
        </div>

        {isPending && <p className="text-muted text-sm">Loading…</p>}

        {data && (
          <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-1">
            <DashboardPanel
              title="Cited alongside"
              meta="co-citation"
              footer="Counted, not clustered: how many of our papers cite both."
            >
              <ol className="m-0 list-none p-0">
                {data.co_cited.map((work, i) => (
                  <li
                    key={work.arxiv_id}
                    aria-current={work.arxiv_id === reading ? "true" : undefined}
                    className={cn(
                      "border-line relative border-b py-2 pr-2 pl-6.5",
                      work.arxiv_id === reading && "bg-teal-soft",
                    )}
                  >
                    <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                      {i + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => read(work.arxiv_id)}
                      className={TITLE_BUTTON}
                    >
                      {work.title ?? work.arxiv_id}
                    </button>
                    <span className="text-muted mt-0.5 block font-mono text-[10.5px]">
                      {work.cite_both} papers cite both
                    </span>
                  </li>
                ))}
              </ol>
            </DashboardPanel>

            <DashboardPanel
              title="Recent papers citing it"
              meta="indexed"
              footer={
                // Three honest numbers: shown, indexed, and the real total.
                // Collapsing any two of them overstates what the agent read.
                <>
                  Showing {data.indexed_citers.length} of the {data.scope_size} papers we indexed;{" "}
                  {data.total_citers.toLocaleString()} cite it in all.
                </>
              }
            >
              <ol className="m-0 list-none p-0">
                {data.indexed_citers.map((citer, i) => (
                  <li
                    key={citer.arxiv_id}
                    aria-current={citer.arxiv_id === reading ? "true" : undefined}
                    className={cn(
                      "border-line relative border-b py-2 pr-2 pl-6.5",
                      citer.arxiv_id === reading && "bg-teal-soft",
                    )}
                  >
                    <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                      {i + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => read(citer.arxiv_id)}
                      className={TITLE_BUTTON}
                    >
                      {citer.title}
                    </button>
                    <span className="text-muted mt-0.5 block font-mono text-[10.5px]">
                      {citer.primary_category} · arXiv:{citer.arxiv_id}
                    </span>
                  </li>
                ))}
              </ol>
            </DashboardPanel>
          </div>
        )}
      </div>
    </div>
  );
}
