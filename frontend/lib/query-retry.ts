import { ApiError } from "@/lib/api-client";

/** How many times a genuinely failed request is retried — TanStack's own
 * default, restated because the rule below replaces `retry` wholesale. */
const TRANSIENT_RETRIES = 3;

/** TanStack's `retry` for a query whose 404 is an answer rather than a fault.
 *
 * Retrying a missing record cannot find it, and something is usually waiting
 * on the miss: `use-viewer-paper.ts` only looks in the citation graph once the
 * corpus has said no, so three backed-off retries there are three seconds of
 * "Loading…" on a paper we could have opened immediately. Transient failures
 * still get the default retries. */
export function retryUnlessMissing(failureCount: number, error: Error): boolean {
  return !(error instanceof ApiError && error.status === 404) && failureCount < TRANSIENT_RETRIES;
}
