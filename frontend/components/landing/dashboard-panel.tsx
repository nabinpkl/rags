import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The frame every region of the dashboard renders into: one border, one
 * padding scale, one header shape (title, optional right-aligned meta,
 * optional one-line subtitle). A region that wants a different frame is a
 * region that does not belong on this canvas.
 *
 * `h-full` on the section plus `min-h-0 flex-1` on the body is what lets a
 * panel fill whatever height its grid row hands it, so two panels sharing a
 * row end level instead of one trailing a band of empty panel.
 */
export function DashboardPanel({
  title,
  meta,
  description,
  footer,
  children,
  className,
  bodyClassName,
}: {
  title: string;
  /** Short right-aligned fact about the panel's own contents (a span, a
   * version). Not a control, and never a second heading. */
  meta?: ReactNode;
  /** What the reader cannot work out from the content itself, in one line. */
  description?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn(
        "bg-panel border-line flex h-full min-w-0 flex-col rounded-md border shadow-xs",
        className,
      )}
    >
      <header className="flex flex-col gap-0.5 px-4 pt-3.5 pb-3">
        {/* Wraps rather than truncates: the title names the panel, and a
            clipped name is worse than a meta line that drops below it. */}
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h2 className="font-serif text-ink min-w-0 text-[17px] leading-tight font-semibold text-balance">
            {title}
          </h2>
          {meta && (
            <span className="text-muted ml-auto shrink-0 font-mono text-[11px] whitespace-nowrap tabular-nums">
              {meta}
            </span>
          )}
        </div>
        {description && (
          <p className="text-muted max-w-[65ch] text-[12.5px] leading-snug">{description}</p>
        )}
      </header>
      <div className={cn("flex min-h-0 flex-1 flex-col px-4 pb-4", bodyClassName)}>{children}</div>
      {footer && (
        <footer className="border-line text-muted border-t px-4 py-2.5 text-[11.5px]">
          {footer}
        </footer>
      )}
    </section>
  );
}
