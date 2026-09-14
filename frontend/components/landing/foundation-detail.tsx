"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Layers, Quote } from "lucide-react";
import Link from "next/link";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { type Foundation, fetchFoundation } from "@/lib/api-client";
import { arxivAbsUrl } from "@/lib/arxiv-links";

/** Every paper on this page opens in OUR reader, not on arxiv.org.
 *
 * The viewer resolves an id against the corpus and then against the citation
 * graph (`hooks/use-viewer-paper.ts`), so a co-cited work we never held text
 * for still opens — its PDF was always arXiv's to serve, fetched by the
 * reader's browser (§6b). That is what lets one link shape cover both lists
 * here instead of sorting papers into ours and theirs on screen. */
function readerHref(arxivId: string): string {
  return `/app?paper=${encodeURIComponent(arxivId)}`;
}

/** The evidence behind one number on the page.
 *
 * Three numbers, none of them interchangeable: total_citers is every paper
 * that cites the work; scope_size is how many of those we indexed and the
 * agent therefore reads; indexed_citers is the capped list shown here. Every
 * listed one opens (D16), and stating all three is the whole reason no
 * `readable` badge is needed on the wire.
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
        <Link
          href={readerHref(foundation.arxiv_id)}
          className="font-serif text-ink hover:text-teal-ink hover:underline"
        >
          {foundation.title ?? foundation.arxiv_id}
        </Link>
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
          className="bg-teal-deep hover:bg-teal-deep-hover focus-visible:outline-teal rounded px-3.5 py-2 text-sm font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Ask about these papers
        </button>
        {/* The heading links here too; this states the affordance for a
            reader who does not try clicking a heading. */}
        <Link
          href={readerHref(foundation.arxiv_id)}
          className="border-line bg-panel text-ink hover:bg-paper flex items-center gap-1.5 rounded border px-3.5 py-2 text-sm font-medium transition-colors motion-reduce:transition-none"
        >
          <BookOpen className="size-4" aria-hidden />
          Read the paper
        </Link>
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
        <p className="text-muted text-sm">Could not load the papers behind this number.</p>
      )}
      {isPending && <p className="text-muted text-sm">Loading…</p>}

      {data && (
        <div className="grid items-start gap-4 md:grid-cols-2">
          <DashboardPanel
            icon={Layers}
            title="Cited alongside"
            meta="co-citation"
            footer="Counted, not clustered: how many of our papers cite both."
          >
            <ol className="m-0 list-none p-0">
              {data.co_cited.map((work, i) => (
                <li key={work.arxiv_id} className="border-line relative border-b py-2 pl-6.5">
                  <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                    {i + 1}
                  </span>
                  <Link
                    href={readerHref(work.arxiv_id)}
                    className="font-serif text-teal-ink block text-[14.5px] hover:underline"
                  >
                    {work.title ?? work.arxiv_id}
                  </Link>
                  <span className="text-muted mt-0.5 block font-mono text-[10.5px]">
                    {work.cite_both} papers cite both
                  </span>
                </li>
              ))}
            </ol>
          </DashboardPanel>

          <DashboardPanel
            icon={Quote}
            title="Recent papers citing it"
            meta="indexed"
            footer={
              // Three honest numbers: shown, indexed, and the real total.
              // Collapsing any two of them overstates what the agent read.
              <>
                Showing {data.indexed_citers.length} of the {data.scope_size} papers we indexed;{" "}
                {data.total_citers.toLocaleString()} cite it in all. Each opens in the reader.
              </>
            }
          >
            <ol className="m-0 list-none p-0">
              {data.indexed_citers.map((citer, i) => (
                <li key={citer.arxiv_id} className="border-line relative border-b py-2 pl-6.5">
                  <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                    {i + 1}
                  </span>
                  <Link
                    href={readerHref(citer.arxiv_id)}
                    className="font-serif text-teal-ink block text-[14.5px] hover:underline"
                  >
                    {citer.title}
                  </Link>
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
  );
}
