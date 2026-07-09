"""Golden JSON for the SSE event vocabulary (spec §4c) — the contract
`frontend/lib/sse.ts` will mirror under test. Also covers the `translate()`
mapping from every loop `EventKind`, and §6c test-first:
`tool_result_summary` never carries a text/content field, error path
included."""

from askrag.agent.loop import AgentEvent, EventKind, StopReason, TurnResult
from askrag.api import sse_events
from askrag.traces import Citation as TraceCitation
from askrag.traces import ToolCallRecord

# --- golden shapes -----------------------------------------------------


def test_thinking_event_shape():
    event = sse_events.ThinkingEvent(text="considering the question")
    assert sse_events.serialize(event) == {
        "type": "thinking",
        "text": "considering the question",
    }


def test_tool_call_event_shape():
    event = sse_events.ToolCallEvent(name="search_corpus", args={"query": "chain of thought"})
    assert sse_events.serialize(event) == {
        "type": "tool_call",
        "name": "search_corpus",
        "args": {"query": "chain of thought"},
    }


def test_tool_result_summary_event_shape():
    event = sse_events.ToolResultSummaryEvent(name="search_corpus", ok=True, error=None)
    assert sse_events.serialize(event) == {
        "type": "tool_result_summary",
        "name": "search_corpus",
        "ok": True,
        "error": None,
    }


def test_ui_action_event_shape():
    event = sse_events.UiActionEvent(
        action="open_paper", args={"action": "open_paper", "paper_id": "2401.00001"}
    )
    assert sse_events.serialize(event) == {
        "type": "ui_action",
        "action": "open_paper",
        "args": {"action": "open_paper", "paper_id": "2401.00001"},
    }


def test_text_event_shape():
    event = sse_events.TextEvent(text="There are 6460 papers.")
    assert sse_events.serialize(event) == {"type": "text", "text": "There are 6460 papers."}


def test_cost_event_shape():
    event = sse_events.CostEvent(cost_usd=0.0123, tokens_in=1500, tokens_out=150)
    assert sse_events.serialize(event) == {
        "type": "cost",
        "cost_usd": 0.0123,
        "tokens_in": 1500,
        "tokens_out": 150,
    }


def test_done_event_shape():
    event = sse_events.DoneEvent(stop_reason="end_turn", run_id="abc123")
    assert sse_events.serialize(event) == {
        "type": "done",
        "stop_reason": "end_turn",
        "run_id": "abc123",
        "citations": (),
    }


def test_done_event_shape_with_citations():
    event = sse_events.DoneEvent(
        stop_reason="end_turn",
        run_id="abc123",
        citations=(sse_events.Citation(paper_id="2401.00001", chunk_ids=("2401.00001#0",)),),
    )
    assert sse_events.serialize(event) == {
        "type": "done",
        "stop_reason": "end_turn",
        "run_id": "abc123",
        "citations": ({"paper_id": "2401.00001", "chunk_ids": ("2401.00001#0",)},),
    }


# --- §6c: tool_result_summary never carries content, error path included ---


def test_tool_result_summary_never_carries_a_text_or_content_field():
    ok_event = sse_events.ToolResultSummaryEvent(name="read_paper", ok=True)
    error_event = sse_events.ToolResultSummaryEvent(
        name="read_paper", ok=False, error="tool crashed"
    )
    for payload in (sse_events.serialize(ok_event), sse_events.serialize(error_event)):
        assert set(payload) == {"type", "name", "ok", "error"}
        assert "content" not in payload
        assert "text" not in payload


# --- translate(): every loop EventKind ----------------------------------


def test_translate_tool_call_maps_to_tool_call_event():
    event = AgentEvent(EventKind.TOOL_CALL, {"name": "search_corpus", "args": {"query": "x"}})
    sse = sse_events.translate(event)
    assert sse == sse_events.ToolCallEvent(name="search_corpus", args={"query": "x"})


def test_translate_drive_ui_tool_call_maps_to_ui_action_not_tool_call():
    args = {"action": "goto_page", "paper_id": "2401.00001", "page": 3}
    event = AgentEvent(EventKind.TOOL_CALL, {"name": "drive_ui", "args": args})
    sse = sse_events.translate(event)
    assert sse == sse_events.UiActionEvent(action="goto_page", args=args)
    assert not isinstance(sse, sse_events.ToolCallEvent)


def test_translate_tool_result_maps_to_tool_result_summary():
    event = AgentEvent(EventKind.TOOL_RESULT, {"name": "read_paper", "ok": False, "error": "boom"})
    sse = sse_events.translate(event)
    assert sse == sse_events.ToolResultSummaryEvent(name="read_paper", ok=False, error="boom")


def test_translate_tool_result_success_has_no_error_key_leaking_through():
    # The loop's own success TOOL_RESULT data has no "error" key at all
    # (askrag/agent/loop.py's _dispatch_tool_calls) — translate() must not
    # choke on its absence.
    event = AgentEvent(EventKind.TOOL_RESULT, {"name": "search_corpus", "ok": True})
    sse = sse_events.translate(event)
    assert sse == sse_events.ToolResultSummaryEvent(name="search_corpus", ok=True, error=None)


def test_translate_text_maps_to_text_event():
    event = AgentEvent(EventKind.TEXT, {"text": "the answer"})
    assert sse_events.translate(event) == sse_events.TextEvent(text="the answer")


def test_translate_done_maps_to_done_event():
    event = AgentEvent(EventKind.DONE, {"stop_reason": "end_turn", "run_id": "r1"})
    assert sse_events.translate(event) == sse_events.DoneEvent(stop_reason="end_turn", run_id="r1")


# --- cost/done builders from TurnResult ----------------------------------


def _turn_result(
    *, stop_reason: StopReason = StopReason.END_TURN, run_id: str = "r2"
) -> TurnResult:
    return TurnResult(
        text="answer",
        stop_reason=stop_reason,
        tool_calls=(),
        tokens_in=1000,
        tokens_out=50,
        cost_usd=0.0042,
        run_id=run_id,
        messages=[],
    )


def test_cost_event_from_turn_result():
    result = _turn_result()
    assert sse_events.cost_event(result) == sse_events.CostEvent(
        cost_usd=0.0042, tokens_in=1000, tokens_out=50
    )


def test_done_event_from_turn_result():
    result = _turn_result(stop_reason=StopReason.STEP_CAP, run_id="r3")
    assert sse_events.done_event(result) == sse_events.DoneEvent(
        stop_reason="step_cap", run_id="r3"
    )


def test_done_event_from_turn_result_aggregates_citations_across_tool_calls():
    tool_calls = (
        ToolCallRecord(
            name="search_corpus",
            args={"query": "a"},
            ok=True,
            citations=(
                TraceCitation(paper_id="2401.00001", chunk_id="2401.00001#0"),
                TraceCitation(paper_id="2401.00001", chunk_id="2401.00001#1"),
            ),
        ),
        ToolCallRecord(
            name="search_corpus",
            args={"query": "b"},
            ok=True,
            citations=(TraceCitation(paper_id="2401.00002", chunk_id="2401.00002#0"),),
        ),
        ToolCallRecord(name="query_metadata", args={"op": "corpus_stats"}, ok=True),
    )
    result = TurnResult(
        text="answer",
        stop_reason=StopReason.END_TURN,
        tool_calls=tool_calls,
        tokens_in=1000,
        tokens_out=50,
        cost_usd=0.0042,
        run_id="r4",
        messages=[],
    )
    event = sse_events.done_event(result)
    assert event.citations == (
        sse_events.Citation(paper_id="2401.00001", chunk_ids=("2401.00001#0", "2401.00001#1")),
        sse_events.Citation(paper_id="2401.00002", chunk_ids=("2401.00002#0",)),
    )


# --- citations_from_tool_calls: dedup + first-seen order ------------------


def test_citations_from_tool_calls_dedupes_repeated_chunk_ids_within_one_paper():
    tool_calls = (
        ToolCallRecord(
            name="search_corpus",
            args={"query": "a"},
            ok=True,
            citations=(
                TraceCitation(paper_id="2401.00001", chunk_id="2401.00001#0"),
                TraceCitation(paper_id="2401.00001", chunk_id="2401.00001#0"),
            ),
        ),
    )
    assert sse_events.citations_from_tool_calls(tool_calls) == (
        sse_events.Citation(paper_id="2401.00001", chunk_ids=("2401.00001#0",)),
    )


def test_citations_from_tool_calls_empty_when_no_calls_carry_citations():
    tool_calls = (ToolCallRecord(name="query_metadata", args={"op": "corpus_stats"}, ok=True),)
    assert sse_events.citations_from_tool_calls(tool_calls) == ()
