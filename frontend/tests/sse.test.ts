// Golden JSON mirroring `backend/tests/test_sse_events.py` — the contract
// this file's parseSseEvent() is tested against. If a shape here drifts from
// the backend's `serialize()` output, the contract is broken.
import { describe, expect, it } from "vitest";
import { parseSseEvent } from "@/lib/sse";

describe("parseSseEvent — golden shapes", () => {
  it("parses a thinking event", () => {
    const raw = JSON.stringify({ type: "thinking", text: "considering the question" });
    expect(parseSseEvent(raw)).toEqual({ type: "thinking", text: "considering the question" });
  });

  it("parses a tool_call event", () => {
    const raw = JSON.stringify({
      type: "tool_call",
      name: "search_corpus",
      args: { query: "chain of thought" },
    });
    expect(parseSseEvent(raw)).toEqual({
      type: "tool_call",
      name: "search_corpus",
      args: { query: "chain of thought" },
    });
  });

  it("parses a tool_result_summary event — name + ok/error only", () => {
    const raw = JSON.stringify({
      type: "tool_result_summary",
      name: "search_corpus",
      ok: true,
      error: null,
    });
    const event = parseSseEvent(raw);
    expect(event).toEqual({
      type: "tool_result_summary",
      name: "search_corpus",
      ok: true,
      error: null,
    });
    expect(Object.keys(event as object).sort()).toEqual(["error", "name", "ok", "type"]);
  });

  it("parses a tool_result_summary error path with no content/text field", () => {
    const raw = JSON.stringify({
      type: "tool_result_summary",
      name: "read_paper",
      ok: false,
      error: "tool crashed",
    });
    const event = parseSseEvent(raw) as unknown as Record<string, unknown>;
    expect(event).toEqual({
      type: "tool_result_summary",
      name: "read_paper",
      ok: false,
      error: "tool crashed",
    });
    expect(event).not.toHaveProperty("content");
    expect(event).not.toHaveProperty("text");
  });

  it("parses a ui_action event", () => {
    const raw = JSON.stringify({
      type: "ui_action",
      action: "open_paper",
      args: { action: "open_paper", paper_id: "2401.00001" },
    });
    expect(parseSseEvent(raw)).toEqual({
      type: "ui_action",
      action: "open_paper",
      args: { action: "open_paper", paper_id: "2401.00001" },
    });
  });

  it("parses a text event", () => {
    const raw = JSON.stringify({ type: "text", text: "There are 6460 papers." });
    expect(parseSseEvent(raw)).toEqual({ type: "text", text: "There are 6460 papers." });
  });

  it("parses a cost event", () => {
    const raw = JSON.stringify({
      type: "cost",
      cost_usd: 0.0123,
      tokens_in: 1500,
      tokens_out: 150,
    });
    expect(parseSseEvent(raw)).toEqual({
      type: "cost",
      cost_usd: 0.0123,
      tokens_in: 1500,
      tokens_out: 150,
    });
  });

  it("parses a done event", () => {
    const raw = JSON.stringify({
      type: "done",
      stop_reason: "end_turn",
      run_id: "abc123",
      citations: [],
    });
    expect(parseSseEvent(raw)).toEqual({
      type: "done",
      stop_reason: "end_turn",
      run_id: "abc123",
      citations: [],
    });
  });

  it("parses a done event's citations — ids only, D-1/issue #27", () => {
    const raw = JSON.stringify({
      type: "done",
      stop_reason: "end_turn",
      run_id: "abc123",
      citations: [{ paper_id: "2401.00001", chunk_ids: ["2401.00001#0", "2401.00001#1"] }],
    });
    const event = parseSseEvent(raw);
    expect(event).toEqual({
      type: "done",
      stop_reason: "end_turn",
      run_id: "abc123",
      citations: [{ paper_id: "2401.00001", chunk_ids: ["2401.00001#0", "2401.00001#1"] }],
    });
  });
});

describe("parseSseEvent — forward-compat", () => {
  it("returns null for an unknown event type", () => {
    const raw = JSON.stringify({ type: "some_future_event", payload: 42 });
    expect(parseSseEvent(raw)).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseSseEvent("not json")).toBeNull();
  });

  it("returns null for a JSON value with no type field", () => {
    expect(parseSseEvent(JSON.stringify({ text: "no type here" }))).toBeNull();
  });

  it("returns null for a non-object JSON value", () => {
    expect(parseSseEvent(JSON.stringify("just a string"))).toBeNull();
    expect(parseSseEvent(JSON.stringify(42))).toBeNull();
    expect(parseSseEvent(JSON.stringify(null))).toBeNull();
  });
});
