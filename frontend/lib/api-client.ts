// Single base-URL owner (spec §4c) — every network call, REST or SSE, reads
// this constant instead of hardcoding an origin. Empty string resolves to a
// same-origin relative path, correct behind the prod Caddy `/api` reverse
// proxy (D13). Local dev sets NEXT_PUBLIC_API_BASE_URL (e.g.
// http://localhost:8000) to reach `just serve`'s uvicorn origin directly,
// since `next dev` runs on a different port with no proxy configured yet.
// The typed REST fetch wrapper this file is named for lands with the
// explorer issue (#28), the first caller that needs one — this issue only
// needs the base URL, for the SSE hook.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
