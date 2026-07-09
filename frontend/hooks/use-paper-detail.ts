"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchPaperDetail } from "@/lib/api-client";

/** TanStack Query over `GET /api/papers/{id}` (#27). `chunkIds` (from a
 * turn's `citations`, agent-session-store.ts) requests the §6c-capped
 * `excerpts` for the cited-excerpts pane; omitted/empty means "just the
 * paper metadata" (explorer→viewer open with no citation yet). `chunkIds`
 * is joined into the query key so opening the same paper with a different
 * citation set re-fetches instead of serving a stale excerpt list. */
export function usePaperDetail(paperId: string | null, chunkIds: readonly string[] = []) {
  const chunksParam = chunkIds.length > 0 ? chunkIds.join(",") : undefined;

  return useQuery({
    queryKey: ["paper-detail", paperId, chunksParam ?? null],
    queryFn: () => fetchPaperDetail(paperId as string, { chunks: chunksParam }),
    enabled: paperId !== null,
  });
}
