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

function buildQueryString(query: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function getJson<T>(
  path: string,
  query: Record<string, string | number | null | undefined>,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`);
  if (!res.ok) throw new Error(`askrag: GET ${path} failed with ${res.status}`);
  return (await res.json()) as T;
}

/** GET /api/papers — cursor-paginated browse or (q set) bounded search
 * (D-1/D-2, decisions.md). */
export function fetchPapers(query: PapersQuery): Promise<PapersResponse> {
  return getJson("/api/papers", query);
}

/** GET /api/facets — categorical (category/year/license/venue) counts for
 * the facet rail. A different "facet" sense than `PaperListItem.facets`
 * (routes_explorer.py's module docstring, decisions.md Fill-in 2). */
export function fetchFacets(query: FacetsQuery): Promise<FacetsResponse> {
  return getJson("/api/facets", query);
}
