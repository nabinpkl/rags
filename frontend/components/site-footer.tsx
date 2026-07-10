import { ARXIV_ATTRIBUTION, ARXIV_URL, GITHUB_CONTACT_URL, TAKEDOWN_EMAIL } from "@/lib/attribution";

/** Persistent footer carrying arXiv's required attribution + the §6c
 * takedown/contact path. Mounted once in `app/page.tsx`, outside the
 * explorer<->viewer swap and the chat panel, so it renders on every view by
 * placement rather than per-view code. All text/hrefs read from
 * `lib/attribution.ts` — the single source of truth for this legal text. */
export function SiteFooter() {
  return (
    <footer className="bg-panel border-line text-muted flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t px-4 py-2 text-xs">
      <p>{ARXIV_ATTRIBUTION}</p>
      <div className="flex shrink-0 items-center gap-3">
        <a
          href={ARXIV_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-ink underline"
        >
          arXiv
        </a>
        <a
          href={GITHUB_CONTACT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-ink underline"
        >
          Report an issue
        </a>
        <a href={`mailto:${TAKEDOWN_EMAIL}`} className="hover:text-ink underline">
          Takedown request
        </a>
      </div>
    </footer>
  );
}
