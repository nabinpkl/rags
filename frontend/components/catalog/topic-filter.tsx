"use client";

import {
  Atom,
  AudioLines,
  Binary,
  Bot,
  BookOpen,
  BrainCircuit,
  Calculator,
  ChartLine,
  ChartScatter,
  ChevronDown,
  CircleEllipsis,
  CodeXml,
  Database,
  Dna,
  FileSearch,
  Film,
  Gamepad2,
  Gauge,
  Globe,
  Grid3x3,
  Infinity as InfinityIcon,
  Landmark,
  Languages,
  Library,
  Microchip,
  MonitorCog,
  MousePointerClick,
  Network,
  PenTool,
  RadioTower,
  Regex,
  ScanEye,
  Shapes,
  Share2,
  ShieldCheck,
  Sigma,
  SlidersHorizontal,
  Spline,
  SquareFunction,
  Waypoints,
  Workflow,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useId, useState } from "react";

import type { CatalogBucket } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/** How many topics show before the rest fold into "Others". Nine held 89%
 * of the unfiltered catalog on 2026-09-17; the other 108 codes were mostly
 * cross-listed archives of a few papers each. */
export const TOP_TOPICS = 9;

/** One glyph per arXiv cs class, so a topic reads at a glance in the rail.
 * The names come from the API (`askrag/category_names.py`); only the picture
 * is the frontend's. Codes outside cs have no name and share one glyph. */
const TOPIC_ICONS: Record<string, LucideIcon> = {
  "cs.AI": BrainCircuit,
  "cs.AR": Microchip,
  "cs.CC": InfinityIcon,
  "cs.CE": Calculator,
  "cs.CG": Spline,
  "cs.CL": Languages,
  "cs.CR": ShieldCheck,
  "cs.CV": ScanEye,
  "cs.CY": Landmark,
  "cs.DB": Database,
  "cs.DC": Network,
  "cs.DL": Library,
  "cs.DM": Grid3x3,
  "cs.DS": Workflow,
  "cs.ET": Atom,
  "cs.FL": Regex,
  "cs.GL": BookOpen,
  "cs.GR": PenTool,
  "cs.GT": Gamepad2,
  "cs.HC": MousePointerClick,
  "cs.IR": FileSearch,
  "cs.IT": RadioTower,
  "cs.LG": ChartScatter,
  "cs.LO": Binary,
  "cs.MA": Waypoints,
  "cs.MM": Film,
  "cs.MS": SquareFunction,
  "cs.NA": ChartLine,
  "cs.NE": Dna,
  "cs.NI": Globe,
  "cs.OH": CircleEllipsis,
  "cs.OS": MonitorCog,
  "cs.PF": Gauge,
  "cs.PL": CodeXml,
  "cs.RO": Bot,
  "cs.SC": Sigma,
  "cs.SD": AudioLines,
  "cs.SE": Wrench,
  "cs.SI": Share2,
  "cs.SY": SlidersHorizontal,
};

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** The Field facet as a list of topics, largest first.
 *
 * A list rather than a select for this one dimension: the top nine are most
 * of the catalog, and seeing them with their counts is itself an answer to
 * "what is in here". The long tail folds under "Others", whose count is what
 * the fold holds. A topic outside the top nine that is selected (from a
 * shared URL, say) stays on screen, so the active filter is never hidden.
 *
 * Each row is a toggle: pressing the selected topic clears it.
 */
export function TopicFilter({
  buckets,
  selected,
  onSelect,
}: {
  buckets: CatalogBucket[] | undefined;
  selected: string | null;
  onSelect: (value: string | null) => void;
}) {
  const labelId = useId();
  const [expanded, setExpanded] = useState(false);
  if (!buckets || buckets.length === 0) return null;

  const top = buckets.slice(0, TOP_TOPICS);
  const rest = buckets.slice(TOP_TOPICS);
  const pinned = !expanded && rest.find((bucket) => bucket.value === selected);
  const others = rest.reduce((sum, bucket) => sum + bucket.papers, 0);

  const row = (bucket: CatalogBucket) => (
    <li key={bucket.value}>
      <TopicRow
        bucket={bucket}
        active={bucket.value === selected}
        onPress={() => onSelect(bucket.value === selected ? null : bucket.value)}
      />
    </li>
  );

  return (
    <div className="flex flex-col gap-1.5">
      <span
        id={labelId}
        className="text-muted px-0.5 font-mono text-[10px] tracking-[0.14em] uppercase"
      >
        Topic
      </span>
      <ul aria-labelledby={labelId} className="flex flex-col gap-0.5">
        {top.map(row)}
        {pinned && row(pinned)}
        {expanded && rest.map(row)}
        {rest.length > 0 && (
          <li>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setExpanded((open) => !open)}
              className="text-ink hover:bg-panel-hover flex w-full items-center gap-2.5 rounded px-2 py-1.5 text-left text-[13px] transition-colors motion-reduce:transition-none"
            >
              <ChevronDown
                className={cn(
                  "text-muted size-4 shrink-0 transition-transform motion-reduce:transition-none",
                  expanded && "rotate-180",
                )}
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                {expanded ? "Fewer topics" : `Others (${rest.length})`}
              </span>
              {!expanded && <Count papers={others} />}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

function TopicRow({
  bucket,
  active,
  onPress,
}: {
  bucket: CatalogBucket;
  active: boolean;
  onPress: () => void;
}) {
  const Icon = TOPIC_ICONS[bucket.value] ?? Shapes;
  return (
    <button
      type="button"
      aria-pressed={active}
      title={bucket.name ? `${bucket.name} (${bucket.value})` : bucket.value}
      onClick={onPress}
      className={cn(
        "text-ink hover:bg-panel-hover flex w-full items-start gap-2.5 rounded px-2 py-1.5 text-left text-[13px] leading-snug transition-colors motion-reduce:transition-none",
        active && "bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-semibold",
      )}
    >
      <Icon
        className={cn("mt-px size-4 shrink-0", active ? "text-teal-ink" : "text-muted")}
        aria-hidden
      />
      <span className="min-w-0 flex-1 text-balance">{bucket.name ?? bucket.value}</span>
      <Count papers={bucket.papers} />
    </button>
  );
}

function Count({ papers }: { papers: number }) {
  return (
    <span className="text-muted shrink-0 font-mono text-[11.5px] tabular-nums">
      <span aria-hidden>{compact.format(papers)}</span>
      <span className="sr-only">{`, ${papers.toLocaleString()} papers`}</span>
    </span>
  );
}
