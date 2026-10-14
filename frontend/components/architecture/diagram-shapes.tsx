import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** SVG building blocks the architecture diagrams share: a labelled box, an
 * arrow, the arrowhead markers, and the frame each diagram sits in. Every
 * fill and stroke is a theme token, so a diagram flips with the theme like
 * the rest of the page. Text sizes are in viewBox units: the figures are
 * drawn 1000 wide and scroll sideways below 860px rather than shrink their
 * labels past reading size. */

export type Tone = "plain" | "soft" | "teal" | "amber";

const BOX: Record<Tone, string> = {
  plain: "fill-panel stroke-outline",
  soft: "fill-panel-hover stroke-outline",
  teal: "fill-teal-soft stroke-teal-ink",
  // amber-soft and amber-ink are fixed in both themes (the replay banner's
  // pair), so this box keeps its own text colour rather than --ink.
  amber: "fill-amber-soft stroke-amber-ink",
};

export function Box({
  x,
  y,
  w,
  h,
  tone = "plain",
  title,
  lines = [],
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  tone?: Tone;
  title: string;
  lines?: string[];
}) {
  const amber = tone === "amber";
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        strokeWidth={tone === "teal" ? 2 : 1.5}
        className={BOX[tone]}
      />
      <text
        x={x + 18}
        y={y + 34}
        className={cn("font-sans text-[20px] font-bold", amber ? "fill-amber-ink" : "fill-ink")}
      >
        {title}
      </text>
      {lines.map((line, i) => (
        <text
          key={line}
          x={x + 18}
          y={y + 62 + i * 24}
          className={cn("font-sans text-[17px]", amber ? "fill-amber-ink" : "fill-ink-2")}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

/** A one-line monospace pill: a tool name, a count. */
export function Pill({
  x,
  y,
  w,
  label,
  tone = "plain",
}: {
  x: number;
  y: number;
  w: number;
  label: string;
  tone?: Tone;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={38}
        rx={6}
        strokeWidth={tone === "teal" ? 2 : 1.5}
        className={BOX[tone]}
      />
      <text x={x + 16} y={y + 25} className="fill-teal-ink font-mono text-[16px] font-semibold">
        {label}
      </text>
    </g>
  );
}

/** Arrowhead markers, one per stroke colour, ids scoped by `id`. */
export function ArrowDefs({ id }: { id: string }) {
  return (
    <defs>
      {(["ink", "teal", "amber"] as const).map((c) => (
        <marker
          key={c}
          id={`${id}-${c}`}
          viewBox="0 0 10 10"
          refX={9}
          refY={5}
          markerWidth={8}
          markerHeight={8}
          orient="auto-start-reverse"
        >
          <path
            d="M0 0 10 5 0 10z"
            className={
              c === "ink" ? "fill-ink-2" : c === "teal" ? "fill-teal-ink" : "fill-amber-ink"
            }
          />
        </marker>
      ))}
    </defs>
  );
}

export function Arrow({
  d,
  id,
  color = "ink",
  dashed = false,
}: {
  d: string;
  id: string;
  color?: "ink" | "teal" | "amber";
  dashed?: boolean;
}) {
  const stroke =
    color === "ink" ? "stroke-ink-2" : color === "teal" ? "stroke-teal-ink" : "stroke-amber-ink";
  return (
    <path
      d={d}
      fill="none"
      strokeWidth={color === "teal" ? 2.5 : 2}
      strokeDasharray={dashed ? "7 6" : undefined}
      markerEnd={`url(#${id}-${color})`}
      className={stroke}
    />
  );
}

/** A label set on an arrow: monospace, teal for the agent's path. */
export function EdgeLabel({
  x,
  y,
  children,
  mono = true,
}: {
  x: number;
  y: number;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <text
      x={x}
      y={y}
      className={
        mono
          ? "fill-teal-ink font-mono text-[16px] font-semibold"
          : "fill-ink-2 font-sans text-[17px]"
      }
    >
      {children}
    </text>
  );
}

/** The panel a diagram sits in. Below 860px it scrolls inside itself, never
 * the page. */
export function Figure({
  label,
  viewBox,
  children,
  minWidth = 860,
}: {
  label: string;
  viewBox: string;
  children: ReactNode;
  minWidth?: number;
}) {
  return (
    <div className="bg-panel border-outline overflow-x-auto rounded-lg border p-5">
      <svg
        viewBox={viewBox}
        role="img"
        aria-label={label}
        className="block h-auto w-full"
        style={{ minWidth }}
      >
        {children}
      </svg>
    </div>
  );
}
