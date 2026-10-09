"use client";

import { useQuery } from "@tanstack/react-query";

import { usePaperDetail } from "@/hooks/use-paper-detail";
import { fetchFoundation } from "@/lib/api-client";
import type { components } from "@/lib/api-types.gen";
import { retryUnlessMissing } from "@/lib/query-retry";

type CitedExcerpt = components["schemas"]["CitedExcerpt"];

/** What the viewer needs to open a paper: enough to title it, and the version
 * to pin its PDF to (§6b/D9). `indexed` is derived HERE, from which of our own
 * records answered — it is not a field on any response, so D16's "no
 * `readable` flag reaches the wire" still holds. */
export interface ViewerPaper {
  title: string | null;
  authors: string | null;
  year: number | null;
  primary_category: string | null;
  version: string | null;
  excerpts: CitedExcerpt[];
  excerpts_truncated: boolean;
  /** True when we hold this paper's text, so the agent can read it and the
   * excerpts pane can fill. False for a work we only know as a citation
   * target — its PDF still opens, because those bytes were never ours. */
  indexed: boolean;
}

/** Resolves an arxiv id against the corpus first, then against the citation
 * graph.
 *
 * The dashboard links works our cohort CITES — Llama 3, VGG, layer norm — and
 * most of those we never held text for: the frontier manifest indexes the top
 * cited works and their recent citers, not every work anyone cited. Sending
 * those to arxiv.org instead of our own reader was the honest thing while the
 * viewer could only open corpus rows, but it meant two kinds of paper link on
 * one page with nothing visible to explain which was which.
 *
 * Nothing about the PDF needed the corpus: `arxiv-pdf-frame.tsx` fetches
 * arxiv.org from the reader's browser (§6b), and the id alone builds that URL.
 * Only the header's metadata did, and `cited_works` already carries it. So the
 * viewer opens anything we can name, and what the corpus decides is what the
 * AGENT can read — which is a different claim, made in a different place.
 */
export function useViewerPaper(paperId: string | null, chunkIds: readonly string[] = []) {
  const corpus = usePaperDetail(paperId, chunkIds);

  // Second, and only after the corpus has said no: `enabled` keeps this from
  // firing for the common case, where the paper IS indexed.
  //
  // `/api/foundations/{id}` rather than a metadata endpoint of its own — it
  // is already the one route that reads `cited_works`, and the two list limits
  // are pinned to 1 because none of it is rendered here.
  const cited = useQuery({
    queryKey: ["cited-work", paperId],
    queryFn: () => fetchFoundation(paperId as string, { co_cited_limit: 1, citers_limit: 1 }),
    enabled: paperId !== null && corpus.isError,
    // The last place we look: without this, an id in neither record spends
    // three backed-off retries on "Loading…" before admitting it is unknown.
    retry: retryUnlessMissing,
  });

  let data: ViewerPaper | undefined;
  if (corpus.data) {
    data = { ...corpus.data, indexed: true };
  } else if (cited.data) {
    const { title, authors, year, primary_category, version } = cited.data.foundation;
    data = {
      title,
      authors,
      year,
      primary_category,
      version,
      excerpts: [],
      excerpts_truncated: false,
      indexed: false,
    };
  }

  return {
    data,
    isPending: corpus.isPending || (corpus.isError && cited.isPending),
    // Only when BOTH records are missing is the paper genuinely unknown to us.
    isError: corpus.isError && cited.isError,
  };
}
