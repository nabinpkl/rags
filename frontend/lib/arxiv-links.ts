// The one place arxiv.org URLs are built (D9, §6b). Version pinning is the
// point: a bare `/abs/2505.09388` follows the paper as it is revised, so a
// quote or a page number we showed can silently stop matching what the reader
// lands on. Every link we emit names the version we actually read, when we
// know it.
//
// We never serve, proxy, or cache these bytes — the reader's browser fetches
// them from arxiv.org directly (§6b).

const ARXIV_ORIGIN = "https://arxiv.org";

/** `https://arxiv.org/abs/<id>v<N>` — the paper's landing page, version-pinned.
 *
 * `version` is nullable because the catalog does not always carry one; an
 * unpinned URL is the documented fallback (D9), not an error. */
export function arxivAbsUrl(arxivId: string, version?: string | null): string {
  return `${ARXIV_ORIGIN}/abs/${arxivId}${version ?? ""}`;
}

/** `https://arxiv.org/pdf/<id>v<N>` — the PDF bytes, fetched by the browser. */
export function arxivPdfUrl(arxivId: string, version?: string | null): string {
  return `${ARXIV_ORIGIN}/pdf/${arxivId}${version ?? ""}`;
}
