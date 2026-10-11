import { useMemo } from "react";
import type { components } from "@/lib/api-types.gen";

type CitedExcerpt = components["schemas"]["CitedExcerpt"];

interface CitedExcerptsPaneProps {
  excerpts: CitedExcerpt[];
  excerptsTruncated: boolean;
  onJumpToPage: (page: number) => void;
}

function sectionAnchorId(chunkId: string): string {
  return `exc-${chunkId}`;
}

/** §6c row 4/D-1: renders ONLY the chunks the paired `GET /api/papers/{id}
 * ?chunks=` call returned — already word-capped and count-capped
 * SERVER-SIDE (routes_explorer.py's `_cited_excerpts`, the sole route
 * `chunks.text` reaches the wire through). This component adds no
 * additional text, fetches nothing itself, and never lets a reader browse
 * beyond the cited set — there is no sequential-excerpt/full-text path here
 * by construction (grep-verifiable: no other prop or fetch call in this
 * file can carry paper text). The PDF pane (arxiv-pdf-frame.tsx) is the
 * reading surface; "PDF p.N" only jumps it, never substitutes for it.
 *
 * Mounted only when there is at least one excerpt (paper-split-view.tsx). */
export function CitedExcerptsPane({
  excerpts,
  excerptsTruncated,
  onJumpToPage,
}: CitedExcerptsPaneProps) {
  const sections = useMemo(() => {
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const excerpt of excerpts) {
      if (!seen.has(excerpt.section)) {
        seen.add(excerpt.section);
        ordered.push(excerpt.section);
      }
    }
    return ordered;
  }, [excerpts]);

  function scrollToSection(section: string) {
    const first = excerpts.find((e) => e.section === section);
    if (!first) return;
    document
      .getElementById(sectionAnchorId(first.chunk_id))
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  return (
    <aside
      aria-label="Cited excerpts"
      className="bg-panel flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4"
    >
      {/* Docked only: stacked, the disclosure button above this pane already
          names it (paper-split-view.tsx). */}
      <h3 className="text-muted hidden font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase @3xl:block">
        Cited excerpts
      </h3>

      {/* One section has nowhere to jump to. */}
      {sections.length > 1 && (
        <nav aria-label="Sections" className="flex flex-wrap gap-1.5">
          {sections.map((section) => (
            <button
              key={section}
              type="button"
              onClick={() => scrollToSection(section)}
              className="border-line bg-paper text-muted hover:border-teal-ink hover:text-teal-ink flex h-7 items-center rounded border px-2 font-mono text-[10.5px]"
            >
              {section}
            </button>
          ))}
        </nav>
      )}

      <ol className="flex flex-col gap-3">
        {excerpts.map((excerpt) => (
          <li
            key={excerpt.chunk_id}
            id={sectionAnchorId(excerpt.chunk_id)}
            className="border-line bg-paper flex scroll-mt-4 flex-col gap-3 rounded border p-3"
          >
            <blockquote className="text-ink font-serif text-[14px] leading-relaxed">
              &ldquo;{excerpt.text}&rdquo;
            </blockquote>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted min-w-0 truncate font-mono text-[10.5px]">
                {excerpt.section}
              </span>
              <button
                type="button"
                onClick={() => onJumpToPage(excerpt.page_start)}
                className="border-teal-ink text-teal-ink hover:bg-teal-soft flex h-7 shrink-0 items-center rounded border px-2 font-mono text-[10.5px]"
              >
                → PDF p.{excerpt.page_start}
              </button>
            </div>
          </li>
        ))}
      </ol>

      {excerptsTruncated && (
        <p className="text-muted text-[11px]">More was quoted than one answer shows.</p>
      )}
    </aside>
  );
}
