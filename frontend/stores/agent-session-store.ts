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
//
// `replay` was originally a member of THIS union — that conflated turn
// lifecycle with session mode and was a real bug (decisions.md 2026-07-09
// round 2): `applyEvent` reassigns `status` on every event including the
// replayed stream's own tool_call/tool_result_summary/text events, so
// `status: "replay"` set in onopen got clobbered by the replayed stream's
// FIRST event, hiding ReplayBanner for the whole replayed answer. `mode`
// below is orthogonal on purpose: `applyEvent` never touches it.
export type AgentStatus =
  | { kind: "idle" }
  | { kind: "streaming" }
  | { kind: "tool_running"; name: string }
  | { kind: "capped"; reason: string };

// Session mode: set once per turn from the X-AskRAG-Mode response header
// (use-agent-stream.ts's onopen), independent of turn lifecycle above.
export type AgentMode = { kind: "live" } | { kind: "replay"; reason: string };

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
  mode: AgentMode;
  sessionId: string | null;
  turns: Turn[];
  // The citation-verification set (decisions.md 2026-07-08): a paper id
  // lands here only once a tool_call/ui_action that referenced it is
  // confirmed by an ok=true tool_result_summary. message-markdown.tsx reads
  // this to decide chip vs plain text.
  //
  // Deliberately SESSION-scoped, not turn-scoped (round 2 review nit): a chip
  // renders for any paper the agent genuinely accessed (ok=true) at any point
  // this session, even in a later turn's answer that didn't itself touch it —
  // still not a hallucination, since the id really was retrieved/navigated to
  // under this session_id. Narrowing to per-turn would need re-deriving the
  // set from scratch each turn for no anti-hallucination benefit.
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
  mode: { kind: "live" },
  sessionId: null,
  turns: [],
  verifiedPaperIds: new Set(),
  pendingCall: null,

  setSessionId: (id) => set({ sessionId: id }),

  startTurn: (question) =>
    set((state) => ({
      status: { kind: "streaming" },
      // Optimistic default for the new turn — budgets.check() decides fresh
      // per request, so a turn that follows a replay isn't stuck "replay"
      // forever. onopen's setReplay() overrides this if the new response's
      // X-AskRAG-Mode header says otherwise.
      mode: { kind: "live" },
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
  // Sets MODE, not status — applyEvent (above) never touches `mode`, so this
  // survives the replayed stream's own events for the whole turn.
  setReplay: (reason) => set({ mode: { kind: "replay", reason } }),

  reset: () =>
    set({
      status: { kind: "idle" },
      mode: { kind: "live" },
      sessionId: null,
      turns: [],
      verifiedPaperIds: new Set(),
      pendingCall: null,
    }),
}));
