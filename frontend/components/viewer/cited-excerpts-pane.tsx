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
 * reading surface; "PDF p.N" only jumps it, never substitutes for it. */
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
      className="border-line bg-panel h-full min-h-0 overflow-y-auto p-3.5"
    >
      {/* Below `md:` the pane sits inside a disclosure whose button already
          says "Cited excerpts" (paper-split-view.tsx); repeating it there
          reads as two headings for one section. */}
      <h3 className="text-muted mb-1 hidden font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase md:block">
        Cited excerpts
      </h3>
      <p className="text-muted mb-3.5 text-[11px] leading-relaxed">
        Quotes are capped (≤50 words, ≤3 per paper per answer). The PDF is the reading surface; this
        pane shows only what the agent cited.
      </p>

      {sections.length > 0 && (
        <div className="mb-3.5 flex flex-wrap gap-1.5">
          {sections.map((section) => (
            <button
              key={section}
              type="button"
              onClick={() => scrollToSection(section)}
              className="border-line bg-paper text-muted hover:border-teal-ink hover:text-teal-ink rounded border px-2 py-0.75 font-mono text-[10.5px]"
            >
              {section}
            </button>
          ))}
        </div>
      )}

      {excerpts.length === 0 ? (
        <p className="text-muted text-[12px]">
          No cited excerpts yet — ask the agent about this paper.
        </p>
      ) : (
        <div>
          {excerpts.map((excerpt) => (
            <div
              key={excerpt.chunk_id}
              id={sectionAnchorId(excerpt.chunk_id)}
              className="border-line bg-paper mb-2.5 rounded border p-2.5"
            >
              <blockquote className="font-serif text-[13.5px] leading-relaxed">
                &ldquo;{excerpt.text}&rdquo;
              </blockquote>
              <div className="flex items-center justify-between">
                <span className="text-muted font-mono text-[10.5px]">{excerpt.section}</span>
                <button
                  type="button"
                  onClick={() => onJumpToPage(excerpt.page_start)}
                  className="border-teal-ink text-teal-ink hover:bg-teal-soft rounded border px-2 py-0.5 font-mono text-[10.5px]"
                >
                  → PDF p.{excerpt.page_start}
                </button>
              </div>
            </div>
          ))}
          {excerptsTruncated && (
            <p className="text-muted text-[11px] italic">
              More citations exist for this paper than the per-answer cap shows here.
            </p>
          )}
        </div>
      )}
    </aside>
  );
}
