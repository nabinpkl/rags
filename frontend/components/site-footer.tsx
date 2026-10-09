import { ThemeMenu } from "@/components/shell/theme-menu";
import {
  ARXIV_ATTRIBUTION,
  ARXIV_URL,
  GITHUB_CONTACT_URL,
  SOURCE_URL,
  TAKEDOWN_EMAIL,
} from "@/lib/attribution";

/** Persistent footer carrying arXiv's required attribution + the §6c
 * takedown/contact path. Mounted once in `app/page.tsx`, outside the
 * explorer<->viewer swap and the chat panel, so it renders on every view by
 * placement rather than per-view code. All text/hrefs read from
 * `lib/attribution.ts` — the single source of truth for this legal text. */
export function SiteFooter() {
  return (
    <footer className="bg-panel border-line text-muted flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t px-3 py-1.5 text-[10.5px] leading-snug sm:px-4 sm:py-2 sm:text-xs">
      <p>{ARXIV_ATTRIBUTION}</p>
      <div className="flex shrink-0 items-center gap-3 pb-[env(safe-area-inset-bottom)]">
        <a
          href={ARXIV_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-ink underline"
        >
          arXiv
        </a>
        <a
          href={SOURCE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-ink underline"
        >
          Source
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
        {/* The theme control lives in the footer because it is the only element
            that survives both the explorer↔viewer swap and every breakpoint —
            one instance, reachable from every screen (#85). Last in the row so
            it lands at the trailing edge rather than in the bottom-left
            corner, where a wrapped footer would stack it under the browser's
            own corner furniture. */}
        <ThemeMenu />
      </div>
    </footer>
  );
}
