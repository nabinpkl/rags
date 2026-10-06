import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

/** A section folded shut: the page reads without it, and a reader who wants
 * the detail knows where it is. */
export function Disclosure({
  title,
  meta,
  children,
}: {
  title: string;
  /** A short count beside the title, e.g. "93 queries". */
  meta?: string;
  children: ReactNode;
}) {
  return (
    <details className="group border-line bg-panel rounded-md border">
      <summary className="text-ink hover:bg-panel-hover flex cursor-pointer list-none items-center gap-2 rounded-md px-4 py-3 text-[14px] font-semibold transition-colors motion-reduce:transition-none [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="text-muted size-4 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none"
          aria-hidden
        />
        {title}
        {meta && <span className="text-muted text-[13px] font-normal">{meta}</span>}
      </summary>
      <div className="border-line border-t p-4">{children}</div>
    </details>
  );
}
