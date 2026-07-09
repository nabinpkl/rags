"""THE hand-built agent loop (D1/D2): messages, tool dispatch via the
registry, step cap, stop conditions, cost accounting into traces.db, prompt
caching on system+tools. No framework — this file plus context_window.py and
prompts.py is the whole thing (target <=200 lines; >500 is the D2 revisit
trigger for "we're rebuilding an SDK badly").

`ModelClient` is the loop's only seam to an LLM: tests script a fake
satisfying it (house rule — tests never call an API); `AnthropicModelClient`
is the real implementation, built by `anthropic_client_from_settings` from
config alone. The loop never constructs its own client.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import anthropic

from askrag import traces
from askrag.agent.context_window import evict_oldest
from askrag.agent.prompts import SYSTEM_PROMPT, fence
from askrag.config import Settings, get_settings
from askrag.tools import registry
from askrag.traces import Citation, ToolCallRecord


class StopReason(Enum):
    """Why one user-message turn ended (D1/D2) — an explicit state, not
    boolean soup (state-machine rule, .claude/rules/python-backend.md)."""

    END_TURN = "end_turn"  # the model finished on its own
    STEP_CAP = "step_cap"  # max_tool_steps_per_message reached
    TOKEN_BUDGET = "token_budget"  # message_token_budget reached


class EventKind(Enum):
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT = "text"
    DONE = "done"


@dataclass(frozen=True)
class AgentEvent:
    """Minimal, transport-agnostic progress event. NOT the SSE vocabulary —
    `askrag.api.sse_events.translate()` (#24) maps these onto it; only the
    HTTP/SSE transport wiring to the frontend is #30's job."""

    kind: EventKind
    data: dict[str, Any]


def _noop_event(event: AgentEvent) -> None:
    return None


@dataclass(frozen=True)
class TurnResult:
    """One user-message turn's outcome — what a caller (#30's chat route, or
    this module's own smoke CLI) needs to reply and persist the session."""

    text: str
    stop_reason: StopReason
    tool_calls: tuple[ToolCallRecord, ...]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    run_id: str
    messages: list[Any]  # updated running history; pass back into the next turn


class ModelUsage(Protocol):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None


class ModelResponse(Protocol):
    content: list[Any]
    stop_reason: str | None
    usage: ModelUsage


class ModelClient(Protocol):
    def create(
        self, *, system: str, messages: list[Any], tools: list[dict[str, Any]] | None
    ) -> ModelResponse: ...


@dataclass(frozen=True)
class AnthropicModelClient:
    """Wraps `anthropic.Anthropic` + `.messages.create`, with prompt caching
    (D3) on the last system block and the last tool definition — the two
    largest, most stable parts of every call."""

    client: anthropic.Anthropic
    model: str
    max_tokens: int

    def create(
        self, *, system: str, messages: list[Any], tools: list[dict[str, Any]] | None
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tools:
            capped = [dict(t) for t in tools]
            capped[-1] = {**capped[-1], "cache_control": {"type": "ephemeral"}}
            kwargs["tools"] = capped
        return self.client.messages.create(**kwargs)


def anthropic_client_from_settings(settings: Settings) -> AnthropicModelClient:
    """The factory (D2: the loop never builds its own client). Empty
    `agent_api_base_url` => real Anthropic, Haiku (D3, prod unchanged). Set =>
    the OpenRouter cheap-first smoke: the SDK's `base_url` seam points at
    OpenRouter's Anthropic-compatible endpoint (no trailing /v1 — the SDK
    appends /v1/messages itself), authenticated via `auth_token` (Bearer),
    since OpenRouter documents Bearer auth rather than Anthropic's native
    x-api-key header (owner directive 2026-07-06, decisions.md).
    """
    if settings.agent_api_base_url:
        client = anthropic.Anthropic(
            base_url=settings.agent_api_base_url,
            auth_token=settings.openrouter_api_key.get_secret_value(),
        )
        model = settings.smoke_model
    else:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        model = settings.agent_model
    return AnthropicModelClient(
        client=client, model=model, max_tokens=settings.agent_max_output_tokens
    )


def _tool_params() -> list[dict[str, Any]]:
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.json_schema}
        for spec in registry.TOOLS.values()
    ]


def _citations_of(name: str, result: Any) -> tuple[Citation, ...]:
    """(paper_id, chunk_id) pairs a successful tool result retrieved — IDS
    ONLY, never the chunk text alongside them (§6c row 4/D-1, issue #27).

    Only `search_corpus`'s `ScoredChunk`s carry a `chunk_id`; `read_paper`'s
    page-range spans and `query_metadata`'s facts don't, so they contribute
    no citations here (known gap, issue #27 decisions.md: a `read_paper`
    deep-read can't yet drive the cited-excerpts pane, only search hits can).
    Named by tool, mirroring `sse_events.translate()`'s existing
    `name == "drive_ui"` special-case — the same "know one tool's shape at
    the translation boundary" pattern, not a new general interface."""
    if name == "search_corpus":
        return tuple(Citation(paper_id=c.paper_id, chunk_id=c.chunk_id) for c in result.chunks)
    return ()


def _dispatch_tool_calls(
    tool_use_blocks: list[Any], on_event: Callable[[AgentEvent], None]
) -> tuple[list[dict[str, Any]], list[ToolCallRecord]]:
    result_blocks: list[dict[str, Any]] = []
    records: list[ToolCallRecord] = []
    for block in tool_use_blocks:
        name, args = block.name, block.input
        on_event(AgentEvent(EventKind.TOOL_CALL, {"name": name, "args": args}))
        try:
            result = registry.dispatch(name, args)
        except Exception as exc:  # noqa: BLE001 — any tool/schema failure (unknown
            # tool, bad args, a lookup-target that doesn't exist) becomes an
            # is_error tool_result the model can react to, never a crashed turn.
            error = str(exc)
            # Fenced exactly like a success result (§6: the fence is total by
            # construction, not by auditing every tool's exception strings).
            # Today's raise sites only interpolate model-given args, never
            # retrieved corpus text — but a future tool (read_paper,
            # search_corpus) could echo corpus text in an error message, and
            # an unfenced is_error block would then read as MORE trusted than
            # a normal tool_result, exactly backwards. `is_error` still flags
            # the outcome; the content is untrusted like every other result.
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": fence({"error": error}),
                    "is_error": True,
                }
            )
            records.append(ToolCallRecord(name=name, args=args, ok=False, error=error))
            on_event(AgentEvent(EventKind.TOOL_RESULT, {"name": name, "ok": False, "error": error}))
            continue
        result_blocks.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": fence(result.to_model_payload()),
            }
        )
        records.append(
            ToolCallRecord(name=name, args=args, ok=True, citations=_citations_of(name, result))
        )
        on_event(AgentEvent(EventKind.TOOL_RESULT, {"name": name, "ok": True}))
    return result_blocks, records


def _stub_dangling_tool_uses(messages: list[Any]) -> list[Any]:
    """Anthropic requires every tool_use block to get a matching tool_result
    before the next call. When the loop stops mid-tool-use (step cap / token
    budget), satisfy the dangling request with a short refusal instead of
    leaving the transcript API-invalid, so the forced final turn can run."""
    if not messages:
        return messages
    content = messages[-1].get("content")
    if not isinstance(content, list):
        return messages
    pending = [b for b in content if getattr(b, "type", None) == "tool_use"]
    if not pending:
        return messages
    stubs = [
        {
            "type": "tool_result",
            "tool_use_id": b.id,
            "content": "[not run: step/token budget reached]",
            "is_error": True,
        }
        for b in pending
    ]
    return [*messages, {"role": "user", "content": stubs}]


def _text_of(response: ModelResponse) -> str | None:
    blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(blocks) if blocks else None


def run_turn(
    messages: list[Any],
    user_message: str,
    *,
    session_id: str,
    ip: str,
    client: ModelClient,
    settings: Settings | None = None,
    on_event: Callable[[AgentEvent], None] = _noop_event,
) -> TurnResult:
    """Run one user-message turn to completion: append the user message, call
    the model, dispatch any requested tools, repeat until the model stops on
    its own or a cap trips — then always leave the caller with a final answer
    (a forced tools-off synthesis turn on a cap stop, D1/D2)."""
    settings = settings if settings is not None else get_settings()
    started = time.monotonic()

    messages = [*messages, {"role": "user", "content": user_message}]
    tool_params = _tool_params()
    tool_records: list[ToolCallRecord] = []
    # `fresh_in` (input_tokens + cache_creation_input_tokens) is billed at the
    # full input rate; `cache_read` at the reduced rate (D3 prompt caching).
    # Both count toward real context size for the budget check and the
    # persisted `tokens_in` total below — only the PRICE differs, not whether
    # a cache-read token counts as "used". Folding cache_creation into the
    # full input rate is a deliberate approximation: Anthropic actually bills
    # cache WRITES at ~1.25x input, and config has no
    # agent_usd_per_mtok_cache_write — the delta is sub-cent on a few k of
    # system+tools tokens, negligible against the $0.50/day cap (D11).
    fresh_in = out = cache_read = 0
    stop_reason = StopReason.END_TURN
    final_text = ""
    step = 0

    while True:
        messages = evict_oldest(
            messages, ceiling_tokens=settings.message_token_budget, settings=settings
        )
        response = client.create(system=SYSTEM_PROMPT, messages=messages, tools=tool_params)

        fresh_in += response.usage.input_tokens + (response.usage.cache_creation_input_tokens or 0)
        out += response.usage.output_tokens
        cache_read += response.usage.cache_read_input_tokens or 0
        messages = [*messages, {"role": "assistant", "content": response.content}]

        text = _text_of(response)
        if text is not None:
            final_text = text
            on_event(AgentEvent(EventKind.TEXT, {"text": final_text}))

        if response.stop_reason != "tool_use":
            break  # StopReason.END_TURN, the default

        step += 1
        if step > settings.max_tool_steps_per_message:
            stop_reason = StopReason.STEP_CAP
            break
        if fresh_in + cache_read + out > settings.message_token_budget:
            stop_reason = StopReason.TOKEN_BUDGET
            break

        tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        result_blocks, records = _dispatch_tool_calls(tool_use_blocks, on_event)
        tool_records.extend(records)
        messages = [*messages, {"role": "user", "content": result_blocks}]

    if stop_reason is not StopReason.END_TURN:
        messages = _stub_dangling_tool_uses(messages)
        messages = evict_oldest(
            messages, ceiling_tokens=settings.message_token_budget, settings=settings
        )
        response = client.create(system=SYSTEM_PROMPT, messages=messages, tools=None)
        fresh_in += response.usage.input_tokens + (response.usage.cache_creation_input_tokens or 0)
        out += response.usage.output_tokens
        cache_read += response.usage.cache_read_input_tokens or 0
        messages = [*messages, {"role": "assistant", "content": response.content}]
        final_text = _text_of(response) or final_text

    tokens_in = fresh_in + cache_read  # the persisted/reported total, billing-tier-agnostic
    cost_usd = (
        fresh_in / 1_000_000 * settings.agent_usd_per_mtok_in
        + out / 1_000_000 * settings.agent_usd_per_mtok_out
        + cache_read / 1_000_000 * settings.agent_usd_per_mtok_cache_read
    )
    run_id = traces.record_run(
        session_id=session_id,
        ip=ip,
        question=user_message,
        answer_text=final_text,
        tokens_in=tokens_in,
        tokens_out=out,
        cost_usd=cost_usd,
        latency_ms=(time.monotonic() - started) * 1000,
        tool_calls=tool_records,
        showcase=False,
        settings=settings,
    )
    on_event(AgentEvent(EventKind.DONE, {"stop_reason": stop_reason.value, "run_id": run_id}))

    return TurnResult(
        text=final_text,
        stop_reason=stop_reason,
        tool_calls=tuple(tool_records),
        tokens_in=tokens_in,
        tokens_out=out,
        cost_usd=cost_usd,
        run_id=run_id,
        messages=messages,
    )
