// The citation-verification set is the anti-hallucination guard
// (decisions.md 2026-07-08) — the security-relevant behavior of this store,
// tested here directly rather than only indirectly through a component.
import { beforeEach, describe, expect, it } from "vitest";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import type { SseEvent } from "@/lib/sse";

beforeEach(() => {
  useAgentSessionStore.getState().reset();
});

describe("agent-session-store — citation verification", () => {
  it("verifies a paper id read via read_paper only after an ok=true result", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    startTurn("what does this paper say?");

    expect(useAgentSessionStore.getState().verifiedPaperIds.has("2401.00001")).toBe(false);

    applyEvent({ type: "tool_call", name: "read_paper", args: { paper_id: "2401.00001" } });
    expect(useAgentSessionStore.getState().verifiedPaperIds.has("2401.00001")).toBe(false);

    applyEvent({ type: "tool_result_summary", name: "read_paper", ok: true, error: null });
    expect(useAgentSessionStore.getState().verifiedPaperIds.has("2401.00001")).toBe(true);
  });

  it("does NOT verify a paper id whose tool call failed", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    startTurn("q");

    applyEvent({ type: "tool_call", name: "read_paper", args: { paper_id: "9999.99999" } });
    applyEvent({
      type: "tool_result_summary",
      name: "read_paper",
      ok: false,
      error: "no such paper",
    });

    expect(useAgentSessionStore.getState().verifiedPaperIds.has("9999.99999")).toBe(false);
  });

  it("verifies a ui_action(open_paper)'s target, matching its paired result by 'drive_ui' (not 'open_paper')", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    startTurn("open that one");

    applyEvent({
      type: "ui_action",
      action: "open_paper",
      args: { action: "open_paper", paper_id: "1409.7842" },
    });
    applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });

    expect(useAgentSessionStore.getState().verifiedPaperIds.has("1409.7842")).toBe(true);
  });

  it("never verifies an id search_corpus merely surfaced (no paper_id arg to pair against)", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    startTurn("q");

    applyEvent({ type: "tool_call", name: "search_corpus", args: { query: "chain of thought" } });
    applyEvent({ type: "tool_result_summary", name: "search_corpus", ok: true, error: null });

    expect(useAgentSessionStore.getState().verifiedPaperIds.size).toBe(0);
  });
});

describe("agent-session-store — status is one discriminated union", () => {
  it("moves idle -> streaming -> tool_running -> streaming -> idle across a turn", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    expect(useAgentSessionStore.getState().status).toEqual({ kind: "idle" });

    startTurn("q");
    expect(useAgentSessionStore.getState().status).toEqual({ kind: "streaming" });

    applyEvent({ type: "tool_call", name: "search_corpus", args: { query: "x" } });
    expect(useAgentSessionStore.getState().status).toEqual({
      kind: "tool_running",
      name: "search_corpus",
    });

    applyEvent({ type: "tool_result_summary", name: "search_corpus", ok: true, error: null });
    expect(useAgentSessionStore.getState().status).toEqual({ kind: "streaming" });

    applyEvent({ type: "text", text: "the answer" });
    applyEvent({ type: "done", stop_reason: "end_turn", run_id: "r1" });
    expect(useAgentSessionStore.getState().status).toEqual({ kind: "idle" });
    expect(useAgentSessionStore.getState().turns[0].answer).toBe("the answer");
  });

  it("setCapped drives status directly", () => {
    useAgentSessionStore.getState().setCapped("budget exceeded");
    expect(useAgentSessionStore.getState().status).toEqual({
      kind: "capped",
      reason: "budget exceeded",
    });
  });

  it("setReplay drives mode, not status", () => {
    useAgentSessionStore.getState().setReplay("showcase session");
    expect(useAgentSessionStore.getState().mode).toEqual({
      kind: "replay",
      reason: "showcase session",
    });
  });
});

describe("agent-session-store — mode is orthogonal to status (round 2 regression)", () => {
  // The bug: applyEvent reassigned `status` on every event, so a `status:
  // "replay"` set in onopen was clobbered by the replayed stream's own
  // first event, hiding ReplayBanner for the whole replayed answer. `mode`
  // must survive a full run of lifecycle events untouched.
  it("mode stays replay across a full turn of applyEvent calls", () => {
    const { startTurn, applyEvent, setReplay } = useAgentSessionStore.getState();
    startTurn("q");
    setReplay("showcase session");
    expect(useAgentSessionStore.getState().mode).toEqual({
      kind: "replay",
      reason: "showcase session",
    });

    applyEvent({ type: "tool_call", name: "search_corpus", args: { query: "x" } });
    expect(useAgentSessionStore.getState().mode).toEqual({
      kind: "replay",
      reason: "showcase session",
    });

    applyEvent({ type: "tool_result_summary", name: "search_corpus", ok: true, error: null });
    applyEvent({ type: "text", text: "a replayed answer" });
    applyEvent({ type: "done", stop_reason: "end_turn", run_id: "r1" });

    // The lifecycle status still moved normally throughout...
    expect(useAgentSessionStore.getState().status).toEqual({ kind: "idle" });
    // ...while mode, untouched by any of it, still says replay at the end.
    expect(useAgentSessionStore.getState().mode).toEqual({
      kind: "replay",
      reason: "showcase session",
    });
  });

  it("startTurn resets mode to live, so a later live turn isn't stuck replay", () => {
    const { startTurn, setReplay } = useAgentSessionStore.getState();
    startTurn("first question");
    setReplay("showcase session");
    expect(useAgentSessionStore.getState().mode).toEqual({
      kind: "replay",
      reason: "showcase session",
    });

    startTurn("second question");
    expect(useAgentSessionStore.getState().mode).toEqual({ kind: "live" });
  });
});

describe("agent-session-store — forward-compat", () => {
  it("applyEvent does not throw on an event type unknown to this switch", () => {
    const { startTurn, applyEvent } = useAgentSessionStore.getState();
    startTurn("q");
    const futureEvent = { type: "some_future_event" } as unknown as SseEvent;
    expect(() => applyEvent(futureEvent)).not.toThrow();
  });
});
