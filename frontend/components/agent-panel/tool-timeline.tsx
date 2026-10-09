import { Check, Loader2, MousePointerClick, Wrench, X } from "lucide-react";
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

/** The step's state as a glyph, with the word for screen readers. The glyph
 * carries the state at a glance; colour only repeats it. */
function ResultMark({ result }: { result: TimelineEntry["result"] }) {
  if (result === null) {
    return (
      <span className="text-machine-muted">
        <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden />
        <span className="sr-only">running</span>
      </span>
    );
  }
  if (result.ok) {
    return (
      <span className="text-machine-accent">
        <Check className="size-3.5" aria-hidden />
        <span className="sr-only">done</span>
      </span>
    );
  }
  return (
    <span className="text-machine-rust">
      <X className="size-3.5" aria-hidden />
      <span className="sr-only">failed</span>
    </span>
  );
}

/** Renders exactly what the stream carries: a tool's name + args resolving
 * to ok/error — nothing else (DECISIONS.md 2026-07-08). `tool_result_summary`
 * never carries a content field, so there is nothing richer to show: no
 * chunk counts, no scores, no rows, no payloads.
 *
 * One bordered box for the whole run of steps, so a turn's work reads as one
 * object between the question and the answer. A step that drove the reader's
 * screen (`ui_action`) is marked amber with a pointer glyph: it changed what
 * the reader sees, which a search does not.
 *
 * Defensive, not exhaustive, on `entry.call.type`: parseSseEvent() already
 * drops any event type this file doesn't know about, but a future
 * tool_call/ui_action shape reaching this component unrecognized renders a
 * generic row instead of throwing (forward-compat, spec §31 acceptance). */
export function ToolTimeline({ entries }: ToolTimelineProps) {
  if (entries.length === 0) return null;

  return (
    <ol className="border-machine-line flex flex-col gap-2 rounded-lg border px-3 py-2.5">
      {entries.map((entry) => {
        const drivesUi = entry.call.type === "ui_action";
        const Kind = drivesUi ? MousePointerClick : Wrench;
        const args = formatArgs(entry.call.args);
        return (
          <li key={entry.id} className="flex items-start gap-2.5">
            <Kind
              className={cn(
                "mt-0.5 size-3.5 shrink-0",
                drivesUi ? "text-machine-amber" : "text-machine-muted",
              )}
              aria-hidden
            />
            <div className="min-w-0 flex-1 font-mono text-[11.5px] leading-snug">
              <span
                className={cn(
                  "font-semibold",
                  drivesUi ? "text-machine-amber" : "text-machine-text",
                )}
              >
                {callLabel(entry.call) ?? "unknown"}
              </span>
              {args && (
                <span className="text-machine-muted block break-words whitespace-pre-wrap">
                  {args}
                </span>
              )}
              {entry.result && !entry.result.ok && (
                <span className="text-machine-rust block break-words">
                  {entry.result.error ?? "error"}
                </span>
              )}
            </div>
            <span className="mt-0.5 shrink-0">
              <ResultMark result={entry.result} />
            </span>
          </li>
        );
      })}
    </ol>
  );
}
