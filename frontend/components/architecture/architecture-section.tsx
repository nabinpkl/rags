import type { ReactNode } from "react";

/** One section of the Architecture page: a heading, a one-line subtitle,
 * then the figures. Larger than a DashboardPanel header on purpose: this
 * page is read, not scanned, and the diagrams carry it. */
export function ArchitectureSection({
  id,
  title,
  subtitle,
  children,
}: {
  id: string;
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <h2
          id={id}
          className="text-ink font-serif text-[clamp(1.4rem,2.6vw,1.75rem)] leading-tight font-bold"
        >
          {title}
        </h2>
        <p className="text-ink-2 max-w-[62ch] text-[17px] leading-snug">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}
