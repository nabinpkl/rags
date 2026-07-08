"""Reconstructs the SSE event sequence for one showcase trace (#30, D11: the
global-cap-exhausted degrade path). A pure, synchronous generator over an
already-persisted `traces.Run` — no model call, no live loop — so serving a
replay can never spend budget.

Streams "through the same endpoint shape" (spec §4c) as a live turn: a
`tool_call` + `tool_result_summary` pair per recorded `ToolCallRecord`, the
stored `answer_text` as one `text` event, then `cost` + `done` — the exact
event sequence `routes_chat.py` would have streamed live, so the frontend
timeline UI needs no replay-specific code path.
"""

from collections.abc import Iterator
from typing import Any

from askrag.agent.loop import StopReason
from askrag.api import sse_events
from askrag.traces import Run


def replay_events(run: Run) -> Iterator[dict[str, Any]]:
    """Yield `run`'s SSE events, already `sse_events.serialize()`d.

    Showcase traces are curated, COMPLETE turns (D11: "a still-good demo") —
    `traces.Run` has no stored `stop_reason` to reproduce (`loop.py` never
    persists one), so the replayed `done` event always reports `END_TURN`.
    """
    for call in run.tool_calls:
        yield sse_events.serialize(sse_events.ToolCallEvent(name=call.name, args=call.args))
        yield sse_events.serialize(
            sse_events.ToolResultSummaryEvent(name=call.name, ok=call.ok, error=call.error)
        )
    yield sse_events.serialize(sse_events.TextEvent(text=run.answer_text))
    yield sse_events.serialize(
        sse_events.CostEvent(
            cost_usd=run.cost_usd, tokens_in=run.tokens_in, tokens_out=run.tokens_out
        )
    )
    yield sse_events.serialize(
        sse_events.DoneEvent(stop_reason=StopReason.END_TURN.value, run_id=run.run_id)
    )
