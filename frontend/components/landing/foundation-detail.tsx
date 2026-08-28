"use client";

import { useQuery } from "@tanstack/react-query";

import { type Foundation, fetchFoundation } from "@/lib/api-client";
import { arxivAbsUrl } from "@/lib/arxiv-links";

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
    <section className="mx-auto max-w-5xl px-6 py-8">
      <button
        type="button"
        onClick={onBack}
        className="border-line bg-panel text-muted hover:text-ink focus-visible:outline-teal mb-4 rounded-[3px] border px-2.5 py-1 font-mono text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        ← all foundations
      </button>

      <h2 className="font-serif text-ink max-w-[34ch] text-[26px] leading-tight font-semibold">
        {foundation.title ?? foundation.arxiv_id}
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

      <div className="mb-6">
        <button
          type="button"
          onClick={() => onAsk(foundation)}
          disabled={!data?.indexed_citers.length}
          className="bg-teal-deep hover:bg-teal-deep-hover focus-visible:outline-teal rounded px-3.5 py-2 text-sm font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Ask about these papers
        </button>
        <span className="text-muted ml-3 text-xs">
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
        <div className="grid gap-8 md:grid-cols-2">
          <div>
            <h3 className="border-line text-muted mb-2.5 border-b pb-1.5 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
              Cited alongside
            </h3>
            <ol className="m-0 list-none p-0">
              {data.co_cited.map((work, i) => (
                <li key={work.arxiv_id} className="border-line relative border-b py-2 pl-6.5">
                  <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                    {i + 1}
                  </span>
                  <a
                    href={arxivAbsUrl(work.arxiv_id, work.version)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-serif text-teal-ink block text-[14.5px] hover:underline"
                  >
                    {work.title ?? work.arxiv_id}
                  </a>
                  <span className="text-muted mt-0.5 block font-mono text-[10.5px]">
                    {work.cite_both} papers cite both
                  </span>
                </li>
              ))}
            </ol>
            <p className="text-muted mt-2.5 text-[11.5px]">
              Counted, not clustered: how many of our papers cite both.
            </p>
          </div>

          <div>
            <h3 className="border-line text-muted mb-2.5 border-b pb-1.5 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
              Recent papers citing it
            </h3>
            <ol className="m-0 list-none p-0">
              {data.indexed_citers.map((citer, i) => (
                <li key={citer.arxiv_id} className="border-line relative border-b py-2 pl-6.5">
                  <span className="text-muted absolute top-2.5 left-0 font-mono text-[11px]">
                    {i + 1}
                  </span>
                  <a
                    href={`/app?paper=${encodeURIComponent(citer.arxiv_id)}`}
                    className="font-serif text-teal-ink block text-[14.5px] hover:underline"
                  >
                    {citer.title}
                  </a>
                  <span className="text-muted mt-0.5 block font-mono text-[10.5px]">
                    {citer.primary_category} · arXiv:{citer.arxiv_id}
                  </span>
                </li>
              ))}
            </ol>
            <p className="text-muted mt-2.5 text-[11.5px]">
              {/* Three honest numbers: shown, indexed, and the real total.
                  Collapsing any two of them overstates what the agent read. */}
              Showing {data.indexed_citers.length} of the {data.scope_size} papers we indexed;{" "}
              {data.total_citers.toLocaleString()} cite it in all. Each opens in the explorer.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
