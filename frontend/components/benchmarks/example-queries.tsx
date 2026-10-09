"use client";

import { ArrowRight, Target } from "lucide-react";
import { type KeyboardEvent, useCallback, useLayoutEffect, useRef, useState } from "react";

import {
  type Example,
  type GradedPassage,
  ordinal,
  rerankMove,
} from "@/lib/benchmarks/retrieval-benchmark";
import { cn } from "@/lib/utils";

const STRIP = [
  ["rerank", "Rerank"],
  ["hybrid", "Hybrid"],
  ["bm25", "Keyword"],
  ["vector", "Semantic"],
  ["rewrite", "Rewrite"],
] as const;

/** A handful of real queries: where each method ranked the expected passage,
 * then hybrid's top 5 beside the reranked top 5, a line joining each passage
 * the two share. Titles and section names only, never passage text (§6c). */
export function ExampleQueries({ examples, k }: { examples: Example[]; k: number }) {
  const [current, setCurrent] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const e = examples[current];

  function onKey(ev: KeyboardEvent) {
    const step = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const next = (current + step + examples.length) % examples.length;
    setCurrent(next);
    tabs.current[next]?.focus();
  }

  // Container queries, not viewport ones: the docked rail and agent panel can
  // leave this region narrower than a phone on a wide window.
  return (
    <div className="@container">
      <div role="tablist" aria-label="Example queries" className="mb-4 flex flex-wrap gap-2">
        {examples.map((x, i) => {
          const selected = i === current;
          return (
            <button
              key={x.question}
              ref={(el) => {
                tabs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`example-tab-${i}`}
              aria-selected={selected}
              aria-controls="example-panel"
              tabIndex={selected ? 0 : -1}
              title={x.question}
              onClick={() => setCurrent(i)}
              onKeyDown={onKey}
              className={cn(
                "border-line text-ink-2 hover:bg-panel-hover hover:border-outline flex min-h-9 min-w-0 flex-[1_1_100%] items-center gap-2 rounded-md border px-3 py-1.5 text-[13px] transition-colors motion-reduce:transition-none @xl:flex-[1_1_0]",
                selected && "border-teal-ink bg-teal-soft text-ink font-semibold",
              )}
            >
              <span className="min-w-0 truncate">{x.question}</span>
              <MoveBadge rank={x.rank} />
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id="example-panel"
        aria-labelledby={`example-tab-${current}`}
        className="border-line rounded-md border"
      >
        <div className="border-line flex flex-col gap-3 border-b px-3 pt-4 pb-3 @xl:px-5 @xl:pt-5">
          <p className="text-ink text-[17px] leading-snug font-semibold text-balance">
            {e.question}
          </p>
          <ul
            aria-label="Rank of the expected passage"
            className="border-line mt-1 grid grid-cols-5 rounded-md border"
          >
            {STRIP.map(([config, label]) => {
              const r = e.rank[config] ?? null;
              return (
                <li
                  key={config}
                  className="border-line flex flex-col items-center gap-0.5 px-1 py-2 @xl:items-start @xl:px-3 [&+&]:border-l"
                >
                  <span className="text-muted text-[11px] @xl:text-[12px]">{label}</span>
                  <b
                    aria-label={r ? ordinal(r) : `not in top ${k}`}
                    className={cn(
                      "text-[17px] leading-tight tabular-nums @xl:text-[20px]",
                      r ? "text-teal-ink font-bold" : "text-muted font-normal",
                    )}
                  >
                    {r ? ordinal(r) : "–"}
                  </b>
                </li>
              );
            })}
          </ul>
          <p className="text-muted flex min-w-0 items-center gap-2 text-[13px]">
            <Target className="size-[15px] shrink-0" aria-label="Expected passage" />
            <span
              className="text-ink-2 min-w-0 truncate"
              title={`${e.expected.title}, ${e.expected.section}`}
            >
              {e.expected.title}, {e.expected.section}
            </span>
          </p>
        </div>

        <PairedLists left={e.hybrid} right={e.rerank} />

        <div
          aria-hidden
          className="border-line text-muted flex flex-wrap gap-x-5 gap-y-1.5 border-t px-3 py-2.5 text-[12px] @xl:px-5"
        >
          <span className="inline-flex items-center gap-1.5">
            <Mark grade={2} />
            expected passage
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Mark grade={1} />
            same paper, other passage
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Mark grade={0} />
            other paper
          </span>
          <span className="inline-flex items-center gap-1.5">
            <i className="bg-teal-ink h-0.5 w-[18px] rounded-[1px]" />
            where the reranker moved it
          </span>
        </div>
      </div>
    </div>
  );
}

/** Hybrid's rank of the expected passage, then the reranker's. */
function MoveBadge({ rank }: { rank: Record<string, number | null> }) {
  const move = rerankMove(rank);
  const before = rank.hybrid ?? null;
  const after = rank.rerank ?? null;
  const said = `hybrid ${before ? ordinal(before) : "missed"}, rerank ${after ? ordinal(after) : "missed"}`;
  if (move === "missed") {
    return (
      <span className="text-muted ml-auto shrink-0 text-[12px] font-normal" aria-label={said}>
        missed
      </span>
    );
  }
  return (
    <span
      aria-label={said}
      className={cn(
        "ml-auto inline-flex shrink-0 items-center gap-0.5 rounded px-1.5 py-0.5 text-[12px] font-semibold tabular-nums",
        move === "up" && "bg-teal-soft-strong text-teal-ink",
        move === "down" && "bg-amber-soft text-amber-ink",
        move === "same" && "text-muted",
      )}
    >
      {before ?? "–"}
      <ArrowRight className="size-3" aria-hidden />
      {after ?? "–"}
    </span>
  );
}

function Mark({ grade }: { grade: number }) {
  return (
    <i
      className={cn(
        "mt-1 block size-3 shrink-0 rounded-full border-2",
        grade === 2 && "border-teal-ink bg-teal-ink",
        grade === 1 &&
          "border-amber bg-[linear-gradient(90deg,var(--color-amber)_50%,transparent_50%)]",
        grade === 0 && "border-outline",
      )}
    />
  );
}

/** Two ranked lists side by side; on wide layouts an SVG curve joins each
 * passage the two share. Positions are measured, so a ResizeObserver redraws
 * them when wrapping changes a row's height. */
function PairedLists({ left, right }: { left: GradedPassage[]; right: GradedPassage[] }) {
  const box = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<string[]>([]);

  const draw = useCallback(() => {
    const el = box.current;
    if (!el || el.offsetParent === null) return;
    const base = el.getBoundingClientRect();
    const next: string[] = [];
    for (const a of el.querySelectorAll<HTMLElement>("[data-side=left] li")) {
      const b = el.querySelector<HTMLElement>(
        `[data-side=right] li[data-id="${CSS.escape(a.dataset.id ?? "")}"]`,
      );
      if (!b) continue;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      if (ra.right > rb.left) continue; // stacked: no room for a line
      const x1 = ra.right - base.left;
      const y1 = ra.top + ra.height / 2 - base.top;
      const x2 = rb.left - base.left;
      const y2 = rb.top + rb.height / 2 - base.top;
      const mx = (x1 + x2) / 2;
      next.push(`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`);
    }
    setPaths(next);
  }, []);

  useLayoutEffect(() => {
    draw();
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(draw);
    observer.observe(el);
    return () => observer.disconnect();
  }, [draw, left, right]);

  return (
    <div
      ref={box}
      className="relative grid grid-cols-1 gap-4 px-3 py-4 @xl:grid-cols-[minmax(0,1fr)_72px_minmax(0,1fr)] @xl:gap-0 @xl:px-5"
    >
      <svg
        aria-hidden
        className="pointer-events-none absolute inset-0 hidden size-full overflow-visible @xl:block"
      >
        {paths.map((d) => (
          <path key={d} d={d} fill="none" className="stroke-teal-ink" strokeWidth={1.5} />
        ))}
      </svg>
      <RankedList side="left" label="Hybrid" items={left} />
      <div aria-hidden className="hidden @xl:block" />
      <RankedList side="right" label="Reranked" items={right} />
    </div>
  );
}

function RankedList({
  side,
  label,
  items,
}: {
  side: string;
  label: string;
  items: GradedPassage[];
}) {
  return (
    <div data-side={side} className="min-w-0">
      <h3 className="text-muted mb-2 ml-2 text-[11.5px] font-semibold tracking-[0.06em] uppercase">
        {label}
      </h3>
      <ol className="flex flex-col gap-0.5">
        {items.map((x, i) => {
          // A run of passages from one paper prints the title once.
          const cont = i > 0 && items[i - 1].paper === x.paper;
          return (
            <li
              key={x.id}
              data-id={x.id}
              className={cn(
                "grid grid-cols-[16px_12px_minmax(0,1fr)] items-start gap-2 rounded px-2 py-1.5",
                x.grade === 2 && "bg-teal-soft",
              )}
            >
              <span className="text-muted pt-0.5 text-right text-[12px] tabular-nums">{i + 1}</span>
              <Mark grade={x.grade} />
              <span className="min-w-0 text-[13.5px] leading-snug">
                {!cont && (
                  <span className="text-ink block truncate" title={x.title}>
                    {x.title}
                  </span>
                )}
                <span
                  className={cn(
                    "block truncate",
                    cont ? "text-ink-2 text-[13px]" : "text-muted text-[12px]",
                  )}
                  title={x.section}
                >
                  {x.section}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
