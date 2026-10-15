import { ArrowUpRight, X } from "lucide-react";

import { arxivAbsUrl } from "@/lib/arxiv-links";

/** The clicked paper. One link out, version-pinned (D9); nothing here
 * fetches arxiv.org until the reader follows it. */
export function PaperCard({
  arxivId,
  version,
  title,
  theme,
  group,
  onClose,
}: {
  arxivId: string;
  version: string;
  title: string;
  theme: string;
  group: string | null;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label="Paper"
      className="bg-panel border-line absolute right-3 bottom-3 z-10 flex w-[min(380px,calc(100%-24px))] flex-col gap-2 rounded-lg border p-4 shadow-lg"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="text-muted hover:bg-panel-hover hover:text-ink absolute top-2 right-2 flex size-9 items-center justify-center rounded transition-colors motion-reduce:transition-none"
      >
        <X className="size-4" aria-hidden />
      </button>
      <p className="text-muted font-mono text-[14px]">
        {arxivId}
        {version}
      </p>
      <p className="text-ink pr-8 text-[18px] leading-snug font-semibold">{title}</p>
      <p className="text-ink-2 text-[16px]">
        {theme}
        {group && <span className="text-muted"> · in {group}</span>}
      </p>
      <a
        href={arxivAbsUrl(arxivId, version || null)}
        target="_blank"
        rel="noopener noreferrer"
        className="text-teal-ink inline-flex items-center gap-1 self-start text-[16px] font-medium underline-offset-4 hover:underline"
      >
        Open on arXiv
        <ArrowUpRight className="size-4" aria-hidden />
      </a>
    </div>
  );
}
