import type { paths } from "@/lib/api-types.gen";

// Single base-URL owner (spec §4c) — every network call, REST or SSE, reads
// this constant instead of hardcoding an origin. Empty string resolves to a
// same-origin relative path, correct behind the prod Caddy `/api` reverse
// proxy (D13). Local dev sets NEXT_PUBLIC_API_BASE_URL (e.g.
// http://localhost:8000) to reach `just serve`'s uvicorn origin directly,
// since `next dev` runs on a different port with no proxy configured yet.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type PapersQuery = NonNullable<paths["/api/papers"]["get"]["parameters"]["query"]>;
type PapersResponse = paths["/api/papers"]["get"]["responses"][200]["content"]["application/json"];
type FacetsQuery = NonNullable<paths["/api/facets"]["get"]["parameters"]["query"]>;
type FacetsResponse = paths["/api/facets"]["get"]["responses"][200]["content"]["application/json"];
type PaperDetailQuery = NonNullable<paths["/api/papers/{paper_id}"]["get"]["parameters"]["query"]>;
type PaperDetailResponse =
  paths["/api/papers/{paper_id}"]["get"]["responses"][200]["content"]["application/json"];

function buildQueryString(query: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** A non-2xx response, carrying the status so callers can tell "this does not
 * exist" from "the request failed". A 404 is an answer; retrying it only
 * delays the caller's fallback. */
export class ApiError extends Error {
  readonly status: number;

  constructor(path: string, status: number) {
    super(`askrag: GET ${path} failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson<T>(
  path: string,
  query: Record<string, string | number | null | undefined>,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`);
  if (!res.ok) throw new ApiError(path, res.status);
  return (await res.json()) as T;
}

/** GET /api/papers — cursor-paginated browse or (q set) bounded search
 * (D-1/D-2, DECISIONS.md). */
export function fetchPapers(query: PapersQuery): Promise<PapersResponse> {
  return getJson("/api/papers", query);
}

/** GET /api/facets — categorical (category/year/license/venue) counts for
 * the facet rail. A different "facet" sense than `PaperListItem.facets`
 * (routes_explorer.py's module docstring, DECISIONS.md Fill-in 2). */
export function fetchFacets(query: FacetsQuery): Promise<FacetsResponse> {
  return getJson("/api/facets", query);
}

/** GET /api/papers/{paper_id} — paper detail; `chunks` (comma-separated
 * chunk_ids) requests the §6c-CAPPED `CitedExcerpt[]` (routes_explorer.py's
 * `_cited_excerpts` — the sole route through which `chunks.text` reaches the
 * wire). Omitting `chunks` returns `excerpts: []`. */
export function fetchPaperDetail(
  paperId: string,
  query: PaperDetailQuery = {},
): Promise<PaperDetailResponse> {
  return getJson(`/api/papers/${encodeURIComponent(paperId)}`, query);
}

type LandingQuery = NonNullable<paths["/api/landing"]["get"]["parameters"]["query"]>;
export type LandingResponse =
  paths["/api/landing"]["get"]["responses"][200]["content"]["application/json"];
type FoundationQuery = NonNullable<
  paths["/api/foundations/{arxiv_id}"]["get"]["parameters"]["query"]
>;
export type FoundationDetailResponse =
  paths["/api/foundations/{arxiv_id}"]["get"]["responses"][200]["content"]["application/json"];
export type Foundation = LandingResponse["foundations"][number];

/** GET /api/landing — the whole front page in one call. One request because
 * the page is one static composition; N round-trips would only add latency
 * to a view that shows everything at once. */
export function fetchLanding(query: LandingQuery = {}): Promise<LandingResponse> {
  return getJson("/api/landing", query);
}

/** GET /api/foundations/{id} — a foundation's co-cited works and the citing
 * papers we have indexed. The `cited_by` count is every citer; the list is
 * only the readable ones (D16) — render both, never conflate them. */
export function fetchFoundation(
  arxivId: string,
  query: FoundationQuery = {},
): Promise<FoundationDetailResponse> {
  return getJson(`/api/foundations/${encodeURIComponent(arxivId)}`, query);
}

type LatestQuery = NonNullable<paths["/api/latest"]["get"]["parameters"]["query"]>;
export type LatestResponse =
  paths["/api/latest"]["get"]["responses"][200]["content"]["application/json"];
export type LatestPaper = LatestResponse["papers"][number];
export type CoverageResponse =
  paths["/api/coverage"]["get"]["responses"][200]["content"]["application/json"];

/** GET /api/latest — the dashboard's "what just landed" list. Newest
 * INDEXED papers only (D16): every row links to the reader, so an
 * unindexed paper must not appear no matter how fresh it is. */
export function fetchLatest(query: LatestQuery = {}): Promise<LatestResponse> {
  return getJson("/api/latest", query);
}

/** GET /api/coverage — per id-month, what we hold against what arXiv posted.
 * Counts, not lists: the series describes the corpus we collected, including
 * papers the index run has not covered yet. The catalog total travels with
 * each month because a bar without a denominator reads as a fact about the
 * month rather than about our download schedule. */
export function fetchCoverage(): Promise<CoverageResponse> {
  return getJson("/api/coverage", {});
}

export type CategoryCensusResponse =
  paths["/api/census/categories"]["get"]["responses"][200]["content"]["application/json"];
export type CensusMonth = CategoryCensusResponse["months"][number];
export type UptakeResponse =
  paths["/api/census/uptake"]["get"]["responses"][200]["content"]["application/json"];
export type UptakeWork = UptakeResponse["works"][number];

/** GET /api/census/categories — what arXiv cs posted, by primary category,
 * for the months we hold whole. Distinct from /api/coverage: that one is
 * about US (how much of each month we collected), this one is about ARXIV,
 * which only a month above the coverage floor may be spoken for. Months that
 * fail it come back in `excluded` rather than vanishing from the series. */
export function fetchCategoryCensus(): Promise<CategoryCensusResponse> {
  return getJson("/api/census/categories", {});
}

/** GET /api/census/uptake — work from one complete month that the next
 * complete month already cites. */
export function fetchUptake(): Promise<UptakeResponse> {
  return getJson("/api/census/uptake", {});
}
