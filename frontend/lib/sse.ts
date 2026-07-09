// The SSE event vocabulary (spec §4c) — TS mirror of
// `backend/askrag/api/sse_events.py`, pinned 1:1 by `tests/sse.test.ts`
// against that module's golden JSON (`tests/test_sse_events.py`). If the two
// ever disagree the contract is broken; that is the point of the test.
//
// `thinking` is defined for completeness — the loop has no emitter for it
// today (see sse_events.py's ThinkingEvent docstring) — but nothing here
// builds a flow around it.

export interface ThinkingEvent {
  type: "thinking";
  text: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  name: string;
  args: Record<string, unknown>;
}

// §6c boundary: name + ok/error ONLY, never a content/text field. Mirrors
// sse_events.py's ToolResultSummaryEvent — a tool's result payload (chunk
// text, paper text, any retrieved content) must never reach the wire.
export interface ToolResultSummaryEvent {
  type: "tool_result_summary";
  name: string;
  ok: boolean;
  error: string | null;
}

// ADVISORY, NOT VALIDATED (decisions.md 2026-07-07): built from the model's
// raw drive_ui args before corpus.db validation. Consumers must reconcile
// this against the paired `tool_result_summary`, never act on it alone —
// see agent-session-store.ts's verified-paper-id tracking.
export interface UiActionEvent {
  type: "ui_action";
  action: string;
  args: Record<string, unknown>;
}

export interface TextEvent {
  type: "text";
  text: string;
}

export interface CostEvent {
  type: "cost";
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
}

export interface DoneEvent {
  type: "done";
  stop_reason: string;
  run_id: string;
}

export type SseEvent =
  | ThinkingEvent
  | ToolCallEvent
  | ToolResultSummaryEvent
  | UiActionEvent
  | TextEvent
  | CostEvent
  | DoneEvent;

const KNOWN_TYPES: ReadonlySet<SseEvent["type"]> = new Set([
  "thinking",
  "tool_call",
  "tool_result_summary",
  "ui_action",
  "text",
  "cost",
  "done",
]);

/** Parses one SSE `data:` payload. Returns `null` for malformed JSON or an
 * unrecognized `type` — forward-compat with future vocabulary members the
 * backend ships before this file is updated to match. */
export function parseSseEvent(raw: string): SseEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || !("type" in data)) {
    return null;
  }
  const { type } = data as { type: unknown };
  if (typeof type !== "string" || !KNOWN_TYPES.has(type as SseEvent["type"])) {
    return null;
  }
  return data as SseEvent;
}
