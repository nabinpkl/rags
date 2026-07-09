import type { TimelineEntry } from "@/stores/agent-session-store";
import { cn } from "@/lib/utils";

interface ToolTimelineProps {
  entries: TimelineEntry[];
}

function callLabel(call: TimelineEntry["call"]): string | undefined {
  return call.type === "ui_action" ? call.action : call.name;
}

function formatArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  return Object.entries(args)
    .filter(([key]) => key !== "action") // redundant with callLabel() for ui_action
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(" ");
}

function ResultMark({ result }: { result: TimelineEntry["result"] }) {
  if (result === null) return <span>…</span>;
  if (result.ok) return <span className="text-teal">✓ done</span>;
  return <span className="text-rust">✗ {result.error ?? "error"}</span>;
}

/** Renders exactly what the stream carries: a tool's name + args resolving
 * to ok/error — nothing else (decisions.md 2026-07-08). `tool_result_summary`
 * never carries a content field, so there is nothing richer to show: no
 * chunk counts, no scores, no rows, no payloads.
 *
 * Defensive, not exhaustive, on `entry.call.type`: parseSseEvent() already
 * drops any event type this file doesn't know about, but a future
 * tool_call/ui_action shape reaching this component unrecognized renders a
 * generic row instead of throwing (forward-compat, spec §31 acceptance). */
export function ToolTimeline({ entries }: ToolTimelineProps) {
  if (entries.length === 0) return null;

  return (
    <ol className="flex flex-col gap-1.5 font-mono text-[11px]">
      {entries.map((entry) => (
        <li
          key={entry.id}
          className={cn(
            "border-l-2 py-1 pl-2.5",
            entry.call.type === "ui_action" ? "border-amber" : "border-machine-line",
          )}
        >
          <span
            className={cn(
              "font-semibold",
              entry.call.type === "ui_action" ? "text-amber" : "text-teal",
            )}
          >
            {callLabel(entry.call) ?? "unknown"}
          </span>{" "}
          <span className="text-machine-text break-words whitespace-pre-wrap">
            {formatArgs(entry.call.args)}
          </span>
          <div className="text-machine-muted mt-0.5">
            <ResultMark result={entry.result} />
          </div>
        </li>
      ))}
    </ol>
  );
}
