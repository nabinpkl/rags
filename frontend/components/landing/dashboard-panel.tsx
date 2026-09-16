import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The frame every region of the dashboard renders into.
 *
 * It exists so the canvas reads as one instrument rather than a stack of
 * separately-built boxes: one border, one padding scale, one header shape
 * (glyph, title, optional right-aligned meta, optional subtitle). A region
 * that wants a different frame is a region that does not belong on this
 * canvas.
 *
 * `h-full` on the section plus `min-h-0 flex-1` on the body is what lets a
 * panel fill whatever height its grid row hands it — the chart inside sizes
 * its bars as a percentage of that, so two panels sharing a row end level
 * instead of one of them trailing a band of empty panel.
 */
export function DashboardPanel({
  icon: Icon,
  title,
  meta,
  description,
  footer,
  children,
  className,
  bodyClassName,
}: {
  icon: LucideIcon;
  title: string;
  /** Short right-aligned fact about the panel's own contents (a count, a
   * span). Not a control, and never a second heading. */
  meta?: ReactNode;
  /** What the reader cannot work out from the numbers themselves — how they
   * were counted, what they exclude. Muted: it labels the content, it is not
   * the content. */
  description?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn(
        "bg-panel border-line flex h-full min-w-0 flex-col rounded-md border",
        className,
      )}
    >
      <header className="border-line flex items-start gap-2.5 border-b px-4 py-3">
        <span
          className="bg-teal-soft text-teal-ink mt-px grid size-7 shrink-0 place-items-center rounded"
          aria-hidden
        >
          <Icon className="size-[15px]" />
        </span>
        <div className="min-w-0 flex-1">
          {/* Wraps rather than truncates: the title names the panel, and a
              clipped name is worse than a meta line that drops below it. */}
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="font-serif text-ink min-w-0 text-[17px] leading-tight font-semibold text-balance">
              {title}
            </h2>
            {meta && (
              <span className="text-muted ml-auto shrink-0 font-mono text-[10.5px] tracking-[0.08em] whitespace-nowrap uppercase">
                {meta}
              </span>
            )}
          </div>
          {description && (
            <p className="text-muted mt-1 max-w-[74ch] text-[12.5px] leading-relaxed">
              {description}
            </p>
          )}
        </div>
      </header>
      <div className={cn("flex min-h-0 flex-1 flex-col p-4", bodyClassName)}>{children}</div>
      {footer && (
        <footer className="border-line text-muted border-t px-4 py-2.5 font-mono text-[11px]">
          {footer}
        </footer>
      )}
    </section>
  );
}
