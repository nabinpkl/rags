"""Tests for askrag.api.replay — reconstructs the SSE event sequence for a
showcase trace (#30). Pure/synchronous: no model call, no live loop, so a
`Run` maps directly onto the expected serialized event list."""

from askrag.agent.loop import StopReason
from askrag.api import replay
from askrag.traces import Run, ToolCallRecord


def make_run(
    *,
    run_id: str = "r1",
    created_at: str = "2026-07-08T00:00:00+00:00",
    day: str = "2026-07-08",
    session_id: str = "demo",
    ip_hash: str = "hash",
    question: str = "what is chain of thought?",
    answer_text: str = "Chain of thought prompting elicits step-by-step reasoning.",
    tokens_in: int = 1000,
    tokens_out: int = 200,
    cost_usd: float = 0.012,
    latency_ms: float = 850.0,
    tool_calls: tuple[ToolCallRecord, ...] = (),
    showcase: bool = True,
) -> Run:
    # Named parameters (not **dict overrides): a dataclass constructor's
    # per-field types don't survive a **dict unpack under `ty` (each field
    # widens to the dict's value-type union) — explicit kwargs keep this
    # fixture type-checked.
    return Run(
        run_id=run_id,
        created_at=created_at,
        day=day,
        session_id=session_id,
        ip_hash=ip_hash,
        question=question,
        answer_text=answer_text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        showcase=showcase,
    )


def test_replay_with_no_tool_calls_yields_text_cost_done():
    run = make_run()
    events = list(replay.replay_events(run))
    assert events == [
        {"type": "text", "text": run.answer_text},
        {"type": "cost", "cost_usd": 0.012, "tokens_in": 1000, "tokens_out": 200},
        {"type": "done", "stop_reason": StopReason.END_TURN.value, "run_id": "r1"},
    ]


def test_replay_emits_a_tool_call_and_result_pair_per_recorded_call():
    call = ToolCallRecord(name="search_corpus", args={"query": "cot"}, ok=True)
    run = make_run(tool_calls=(call,))
    events = list(replay.replay_events(run))
    assert events[0] == {"type": "tool_call", "name": "search_corpus", "args": {"query": "cot"}}
    assert events[1] == {
        "type": "tool_result_summary",
        "name": "search_corpus",
        "ok": True,
        "error": None,
    }
    assert events[2]["type"] == "text"
    assert events[-1]["type"] == "done"


def test_replay_preserves_error_on_a_failed_recorded_call():
    call = ToolCallRecord(
        name="read_paper", args={"paper_id": "bogus"}, ok=False, error="no such paper"
    )
    run = make_run(tool_calls=(call,))
    events = list(replay.replay_events(run))
    assert events[1] == {
        "type": "tool_result_summary",
        "name": "read_paper",
        "ok": False,
        "error": "no such paper",
    }


def test_replay_orders_multiple_tool_calls_before_the_text_event():
    calls = (
        ToolCallRecord(name="search_corpus", args={"query": "a"}, ok=True),
        ToolCallRecord(name="read_paper", args={"paper_id": "2401.00001"}, ok=True),
    )
    run = make_run(tool_calls=calls)
    events = list(replay.replay_events(run))
    types = [e["type"] for e in events]
    assert types == [
        "tool_call",
        "tool_result_summary",
        "tool_call",
        "tool_result_summary",
        "text",
        "cost",
        "done",
    ]


def test_replay_events_are_already_serialized_plain_dicts():
    run = make_run()
    for event in replay.replay_events(run):
        assert isinstance(event, dict)
        assert "type" in event
