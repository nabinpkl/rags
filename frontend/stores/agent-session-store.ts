// UI/session state for the agent panel (spec §4c, frontend rules: client
// state lives in zustand, never mirrored server state). The single SSE
// connection owner (hooks/use-agent-stream.ts) is the only writer; components
// read slices and never touch `applyEvent`/`pendingCall` directly.
import { create } from "zustand";
import type {
  Citation,
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
// lifecycle with session mode and was a real bug (DECISIONS.md 2026-07-09
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
  // How many steps the timeline held when text last arrived. Text that
  // arrives after further steps is a new segment of the answer (the model
  // wrote a line, called tools, then answered), and it starts a new
  // paragraph instead of running on from the last word.
  stepsAtLastText: number;
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
  // The full ui_action to hand to hooks/use-drive-ui.ts once this call's
  // paired result confirms ok=true — null for a plain tool_call, which only
  // ever feeds verifiedPaperIds above. Captured regardless of whether the
  // action carries a paper_id (D-1, issue #32): a paper-less action like
  // set_filters was previously dropped from reconciliation entirely because
  // this whole record was only built `if paperId`.
  uiAction: UiActionEvent | null;
}

export interface AgentSessionState {
  status: AgentStatus;
  mode: AgentMode;
  sessionId: string | null;
  // The landing-page claim this transcript is about, or null for the whole
  // indexed set. A transcript belongs to one scope: the server refuses to
  // carry history across a scope change (session_store.get_or_create), and
  // use-agent-stream.ts clears the visible turns to match.
  scope: string | null;
  turns: Turn[];
  // The citation-verification set (DECISIONS.md 2026-07-08): a paper id
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
  // paper_id -> cited chunk_ids (#29 seam): the cited-excerpts pane's source
  // for its `?chunks=` fetch (hooks/use-paper-detail.ts). Populated from
  // `done.citations` (ids only — no chunk text ever rides the stream, §6c
  // row 4/D-1). SESSION-scoped and additive like `verifiedPaperIds` above:
  // a paper cited in an earlier turn keeps its excerpts available if the
  // viewer reopens it later, merged (deduped, first-seen order) rather than
  // replaced if a later turn cites the same paper again.
  citationsByPaper: ReadonlyMap<string, readonly string[]>;
  // Internal only: the most recent tool_call/ui_action awaiting its paired
  // tool_result_summary. Not for component consumption.
  pendingCall: PendingCall | null;
  // CONFIRMED ui_actions queue (D-1, issue #32): a ui_action lands here only
  // once its paired tool_result_summary is ok=true — never the raw/
  // provisional ui_action event itself, so a hallucinated or malformed
  // target (drive_ui's own corpus.db check failed) never reaches this queue.
  // hooks/use-drive-ui.ts drains it into viewer-store; this store stays
  // decoupled from viewer-store (D-2) — it only ever produces this queue,
  // never consumes anything from the viewer side.
  confirmedUiActions: readonly UiActionEvent[];

  setSessionId: (id: string) => void;
  startTurn: (question: string, scope?: string | null) => void;
  applyEvent: (event: SseEvent) => void;
  setCapped: (reason: string) => void;
  setReplay: (reason: string) => void;
  // Atomically empties and returns confirmedUiActions — the bridge hook's
  // one-shot drain (D-2: apply each newly-confirmed action exactly once).
  drainConfirmedUiActions: () => readonly UiActionEvent[];
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

/** Dedup + merge, first-seen order — mirrors `sse_events.citations_from_tool_calls`'s
 * own aggregation posture (issue #27 DECISIONS.md) one layer up: a paper's
 * chunk_ids only ever grow across the session, never drop a previously-cited
 * chunk just because a later turn's citation for the same paper is a subset. */
function mergeCitations(
  existing: ReadonlyMap<string, readonly string[]>,
  citations: readonly Citation[],
): ReadonlyMap<string, readonly string[]> {
  if (citations.length === 0) return existing;
  const next = new Map(existing);
  for (const { paper_id: paperId, chunk_ids: chunkIds } of citations) {
    const merged = [...(next.get(paperId) ?? [])];
    for (const chunkId of chunkIds) {
      if (!merged.includes(chunkId)) merged.push(chunkId);
    }
    next.set(paperId, merged);
  }
  return next;
}

export const useAgentSessionStore = create<AgentSessionState>()((set, get) => ({
  status: { kind: "idle" },
  mode: { kind: "live" },
  sessionId: null,
  scope: null,
  turns: [],
  verifiedPaperIds: new Set(),
  citationsByPaper: new Map(),
  pendingCall: null,
  confirmedUiActions: [],

  setSessionId: (id) => set({ sessionId: id }),

  startTurn: (question, scope = null) =>
    set((state) => ({
      status: { kind: "streaming" },
      scope,
      // Optimistic default for the new turn — budgets.check() decides fresh
      // per request, so a turn that follows a replay isn't stuck "replay"
      // forever. onopen's setReplay() overrides this if the new response's
      // X-AskRAG-Mode header says otherwise.
      mode: { kind: "live" },
      turns: [
        ...state.turns,
        {
          id: nextEntryId++,
          question,
          timeline: [],
          answer: "",
          stepsAtLastText: 0,
          cost: null,
          stopReason: null,
        },
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
          // A ui_action is captured regardless of whether it carries a
          // paper_id (D-1, issue #32) — set_filters has none, and dropping
          // it here means it never reaches confirmedUiActions below. A plain
          // tool_call still only needs tracking when it has a paper_id to
          // verify.
          const pendingCall: PendingCall | null =
            event.type === "ui_action"
              ? { resultName: "drive_ui", paperIds: paperId ? [paperId] : [], uiAction: event }
              : paperId
                ? { resultName: event.name, paperIds: [paperId], uiAction: null }
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
          let verifiedPaperIds = state.verifiedPaperIds;
          let confirmedUiActions = state.confirmedUiActions;
          // Apply on CONFIRMED, never provisional (D-1): only an ok=true
          // result for the SAME pending call's resultName reconciles it —
          // drive_ui.run() has already checked the target against corpus.db
          // by the time this fires, so a hallucinated target (ok=false)
          // never verifies a paper id or reaches the ui_action queue.
          if (pendingCall && pendingCall.resultName === event.name && event.ok) {
            if (pendingCall.paperIds.length > 0) {
              verifiedPaperIds = new Set([...state.verifiedPaperIds, ...pendingCall.paperIds]);
            }
            if (pendingCall.uiAction) {
              confirmedUiActions = [...state.confirmedUiActions, pendingCall.uiAction];
            }
          }

          return {
            status: { kind: "streaming" as const },
            turns: replaceLastTurn(state.turns, { ...turn, timeline }),
            pendingCall: null,
            verifiedPaperIds,
            confirmedUiActions,
          };
        }

        case "text": {
          const newSegment = turn.answer.length > 0 && turn.timeline.length > turn.stepsAtLastText;
          return {
            turns: replaceLastTurn(state.turns, {
              ...turn,
              answer: turn.answer + (newSegment ? "\n\n" : "") + event.text,
              stepsAtLastText: turn.timeline.length,
            }),
          };
        }

        case "cost":
          return { turns: replaceLastTurn(state.turns, { ...turn, cost: event }) };

        case "done":
          return {
            status: { kind: "idle" as const },
            turns: replaceLastTurn(state.turns, { ...turn, stopReason: event.stop_reason }),
            citationsByPaper: mergeCitations(state.citationsByPaper, event.citations),
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

  drainConfirmedUiActions: () => {
    const { confirmedUiActions } = get();
    if (confirmedUiActions.length > 0) set({ confirmedUiActions: [] });
    return confirmedUiActions;
  },

  reset: () =>
    set({
      status: { kind: "idle" },
      mode: { kind: "live" },
      sessionId: null,
      scope: null,
      turns: [],
      verifiedPaperIds: new Set(),
      citationsByPaper: new Map(),
      pendingCall: null,
      confirmedUiActions: [],
    }),
}));
