"""The SSE event vocabulary (spec §4c) — the ONE place
`thinking|tool_call|tool_result_summary|ui_action|text|cost|done` are
defined. `frontend/lib/sse.ts` (#26+) and `replay.py` (later) both mirror
this module; it stays transport-agnostic on purpose (no `sse-starlette`, no
FastAPI import) — #30 adds the HTTP/SSE framing on top of what's here.

Each event is a frozen dataclass with a fixed `type` literal;
`serialize()` is the single function turning one into the stable
`{type, ...}` shape pinned by `tests/test_sse_events.py` (the contract
`lib/sse.ts` will be tested against). `translate()` maps
`askrag.agent.loop.AgentEvent` — the loop's minimal, transport-agnostic
progress signal — onto this vocabulary; `cost_event`/`done_event` build the
two members with no loop-emitted `AgentEvent` counterpart (`DONE` already
carries `stop_reason`/`run_id`, so `done_event` mirrors `translate()`'s
`DONE` mapping for callers that only have a `TurnResult`, plus `citations`
(D-1, issue #27) — `translate()` can't compute that field itself, since the
loop's own `AgentEvent(DONE, ...)` carries no `tool_calls` to aggregate;
`cost` has no `EventKind` at all — the loop never emits interim cost).
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from askrag.agent.loop import AgentEvent, EventKind, TurnResult
from askrag.traces import ToolCallRecord


@dataclass(frozen=True)
class ThinkingEvent:
    """Interim reasoning text. The loop has NO emitter for this today — it
    streams only the final answer (`askrag/agent/loop.py`'s `run_turn`
    never emits a THINKING `EventKind`). Defined anyway because replay.py
    and the frontend expect the full seven-member vocabulary; stated here
    honestly rather than fabricated from nothing."""

    text: str
    type: Literal["thinking"] = "thinking"


@dataclass(frozen=True)
class ToolCallEvent:
    name: str
    args: dict[str, Any]
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True)
class ToolResultSummaryEvent:
    """§6c boundary, test-first (`tests/test_sse_events.py`): name + ok/error
    ONLY, on every path including the error one. Never a text/content field
    — a tool_result's payload (chunk text, paper text, any retrieved
    content) must never reach this event. This holds by construction, not
    by an added guard: the loop's own `TOOL_RESULT` `AgentEvent` already
    carries no result payload (`askrag/agent/loop.py`), so `translate()`
    below has nothing to leak even if it wanted to."""

    name: str
    ok: bool
    error: str | None = None
    type: Literal["tool_result_summary"] = "tool_result_summary"


@dataclass(frozen=True)
class UiActionEvent:
    """The `drive_ui` action name + its args, forwarded as the model called
    them. `drive_ui`'s own enum-discriminated schema
    (`askrag/tools/drive_ui.py`) is what makes these args safe to carry
    through untouched here — corpus.db existence-checking still happens at
    tool dispatch, unaffected by this event firing first.

    ADVISORY, NOT VALIDATED (DECISIONS.md 2026-07-07): `translate()` builds
    this from the `TOOL_CALL` `AgentEvent`, i.e. the model's raw args
    *before* `drive_ui.run()` checks the target against corpus.db. A
    hallucinated or malformed target can still produce a `ui_action` here; a
    `tool_result_summary(ok=False)` for the same call follows immediately
    after if `drive_ui` rejects it. Any stream consumer (#26's
    `use-agent-stream.ts`) must treat `ui_action` as provisional and
    reconcile it against the paired `tool_result_summary`, not act on it as
    already-validated."""

    action: str
    args: dict[str, Any]
    type: Literal["ui_action"] = "ui_action"


@dataclass(frozen=True)
class TextEvent:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class CostEvent:
    cost_usd: float
    tokens_in: int
    tokens_out: int
    type: Literal["cost"] = "cost"


@dataclass(frozen=True)
class Citation:
    """One paper's cited chunk ids, ids only — no chunk text ever rides the
    stream (§6c row 4/D-1, issue #27 DECISIONS.md: "ids on the wire, text
    only from the capped `GET /api/papers/{id}?chunks=` endpoint"). Groups
    `traces.Citation` pairs (one per retrieved chunk) by paper_id. A nested
    payload on `DoneEvent`, not its own SSE vocabulary member — no `type`
    field of its own."""

    paper_id: str
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class DoneEvent:
    stop_reason: str
    run_id: str
    citations: tuple[Citation, ...] = ()
    type: Literal["done"] = "done"


SseEvent = (
    ThinkingEvent
    | ToolCallEvent
    | ToolResultSummaryEvent
    | UiActionEvent
    | TextEvent
    | CostEvent
    | DoneEvent
)


def serialize(event: SseEvent) -> dict[str, Any]:
    """The stable `{type, ...}` wire shape — golden-tested by
    `tests/test_sse_events.py`."""
    return asdict(event)


def translate(event: AgentEvent) -> SseEvent | None:
    """Map one loop `AgentEvent` onto its SSE shape. Returns `None` for a
    loop kind with no SSE counterpart — none exists today (every
    `EventKind` maps below), but the signature stays `Optional` so a future
    loop-only progress kind doesn't force a new vocabulary member."""
    if event.kind is EventKind.TOOL_CALL:
        name = event.data["name"]
        args = event.data["args"]
        if name == "drive_ui":
            return UiActionEvent(action=args.get("action", ""), args=args)
        return ToolCallEvent(name=name, args=args)
    if event.kind is EventKind.TOOL_RESULT:
        return ToolResultSummaryEvent(
            name=event.data["name"], ok=event.data["ok"], error=event.data.get("error")
        )
    if event.kind is EventKind.TEXT:
        return TextEvent(text=event.data["text"])
    if event.kind is EventKind.DONE:
        return DoneEvent(stop_reason=event.data["stop_reason"], run_id=event.data["run_id"])
    return None


def citations_from_tool_calls(tool_calls: Sequence[ToolCallRecord]) -> tuple[Citation, ...]:
    """Flatten every call's `traces.Citation` pairs, grouped by paper_id,
    first-seen order (both across calls and within one paper's chunk_ids) —
    the shape D-1/issue #27 puts on the wire. Live turns call this from a
    `TurnResult`'s `tool_calls` (`done_event` below); `replay.py` calls it
    directly from a persisted `Run.tool_calls` — same aggregation, one
    function, so a replayed turn's citations can never drift from a live
    one's."""
    order: list[str] = []
    chunk_ids_by_paper: dict[str, list[str]] = {}
    for call in tool_calls:
        for citation in call.citations:
            bucket = chunk_ids_by_paper.setdefault(citation.paper_id, [])
            if citation.paper_id not in order:
                order.append(citation.paper_id)
            if citation.chunk_id not in bucket:
                bucket.append(citation.chunk_id)
    return tuple(
        Citation(paper_id=paper_id, chunk_ids=tuple(chunk_ids_by_paper[paper_id]))
        for paper_id in order
    )


def cost_event(result: TurnResult) -> CostEvent:
    """The turn's final cost (no intra-turn per-step cost streaming — that's
    deferred to #30/frontend, per the turn-only `TurnResult.cost_usd` the
    loop already computes)."""
    return CostEvent(
        cost_usd=result.cost_usd, tokens_in=result.tokens_in, tokens_out=result.tokens_out
    )


def done_event(result: TurnResult) -> DoneEvent:
    return DoneEvent(
        stop_reason=result.stop_reason.value,
        run_id=result.run_id,
        citations=citations_from_tool_calls(result.tool_calls),
    )
