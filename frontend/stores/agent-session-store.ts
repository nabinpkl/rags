// UI/session state for the agent panel (spec §4c, frontend rules: client
// state lives in zustand, never mirrored server state). The single SSE
// connection owner (hooks/use-agent-stream.ts) is the only writer; components
// read slices and never touch `applyEvent`/`pendingCall` directly.
import { create } from "zustand";
import type {
  CostEvent,
  SseEvent,
  ToolCallEvent,
  ToolResultSummaryEvent,
  UiActionEvent,
} from "@/lib/sse";

// One discriminated union drives rendering (frontend rules: state machines) —
// not accumulating booleans. "tool_running" carries the running tool/action
// name so the panel can say what it's doing, not just that it's doing
// something.
export type AgentStatus =
  | { kind: "idle" }
  | { kind: "streaming" }
  | { kind: "tool_running"; name: string }
  | { kind: "capped"; reason: string }
  | { kind: "replay"; reason: string };

export interface TimelineEntry {
  id: number;
  call: ToolCallEvent | UiActionEvent;
  result: ToolResultSummaryEvent | null;
}

export interface Turn {
  id: number;
  question: string;
  timeline: TimelineEntry[];
  answer: string;
  cost: CostEvent | null;
  stopReason: string | null;
}

interface PendingCall {
  // The name a paired tool_result_summary carries for this call. A
  // ui_action's underlying tool is always "drive_ui" — translate() in
  // sse_events.py keeps the loop's original tool name, not the action name —
  // so a ui_action's pending entry matches on "drive_ui", never on its
  // `action` field.
  resultName: string;
  paperIds: string[];
}

export interface AgentSessionState {
  status: AgentStatus;
  sessionId: string | null;
  turns: Turn[];
  // The citation-verification set (decisions.md 2026-07-08): a paper id
  // lands here only once a tool_call/ui_action that referenced it is
  // confirmed by an ok=true tool_result_summary. message-markdown.tsx reads
  // this to decide chip vs plain text.
  verifiedPaperIds: ReadonlySet<string>;
  // Internal only: the most recent tool_call/ui_action awaiting its paired
  // tool_result_summary. Not for component consumption.
  pendingCall: PendingCall | null;

  setSessionId: (id: string) => void;
  startTurn: (question: string) => void;
  applyEvent: (event: SseEvent) => void;
  setCapped: (reason: string) => void;
  setReplay: (reason: string) => void;
  reset: () => void;
}

let nextEntryId = 0; // module-local: React list keys only, never persisted or compared across sessions

function replaceLastTurn(turns: Turn[], next: Turn): Turn[] {
  return turns.length === 0 ? turns : [...turns.slice(0, -1), next];
}

function paperIdFromArgs(args: Record<string, unknown>): string | null {
  const { paper_id: paperId } = args;
  return typeof paperId === "string" && paperId.length > 0 ? paperId : null;
}

export const useAgentSessionStore = create<AgentSessionState>()((set) => ({
  status: { kind: "idle" },
  sessionId: null,
  turns: [],
  verifiedPaperIds: new Set(),
  pendingCall: null,

  setSessionId: (id) => set({ sessionId: id }),

  startTurn: (question) =>
    set((state) => ({
      status: { kind: "streaming" },
      turns: [
        ...state.turns,
        { id: nextEntryId++, question, timeline: [], answer: "", cost: null, stopReason: null },
      ],
    })),

  applyEvent: (event) =>
    set((state) => {
      const turn = state.turns[state.turns.length - 1];
      if (!turn) return state; // an event with no open turn — nothing to attach it to

      switch (event.type) {
        case "thinking":
          // No emitter today (sse_events.py's ThinkingEvent docstring) —
          // handled by not crashing, not by building a display around it.
          return state;

        case "tool_call":
        case "ui_action": {
          const entry: TimelineEntry = { id: nextEntryId++, call: event, result: null };
          const paperId = paperIdFromArgs(event.args);
          const pendingCall: PendingCall | null = paperId
            ? {
                resultName: event.type === "ui_action" ? "drive_ui" : event.name,
                paperIds: [paperId],
              }
            : null;
          return {
            status: {
              kind: "tool_running" as const,
              name: event.type === "ui_action" ? event.action : event.name,
            },
            turns: replaceLastTurn(state.turns, { ...turn, timeline: [...turn.timeline, entry] }),
            pendingCall,
          };
        }

        case "tool_result_summary": {
          const idx = turn.timeline.findIndex((e) => e.result === null);
          const timeline =
            idx === -1
              ? turn.timeline
              : turn.timeline.map((e, i) => (i === idx ? { ...e, result: event } : e));

          const { pendingCall } = state;
          const verifiedPaperIds =
            pendingCall && pendingCall.resultName === event.name && event.ok
              ? new Set([...state.verifiedPaperIds, ...pendingCall.paperIds])
              : state.verifiedPaperIds;

          return {
            status: { kind: "streaming" as const },
            turns: replaceLastTurn(state.turns, { ...turn, timeline }),
            pendingCall: null,
            verifiedPaperIds,
          };
        }

        case "text":
          return {
            turns: replaceLastTurn(state.turns, { ...turn, answer: turn.answer + event.text }),
          };

        case "cost":
          return { turns: replaceLastTurn(state.turns, { ...turn, cost: event }) };

        case "done":
          return {
            status: { kind: "idle" as const },
            turns: replaceLastTurn(state.turns, { ...turn, stopReason: event.stop_reason }),
          };

        default:
          // Forward-compat: a vocabulary member parseSseEvent() accepts but
          // this switch doesn't yet know how to fold into a turn.
          return state;
      }
    }),

  setCapped: (reason) => set({ status: { kind: "capped", reason } }),
  setReplay: (reason) => set({ status: { kind: "replay", reason } }),

  reset: () =>
    set({
      status: { kind: "idle" },
      sessionId: null,
      turns: [],
      verifiedPaperIds: new Set(),
      pendingCall: null,
    }),
}));
