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

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import anthropic

from askrag import telemetry, traces
from askrag.agent.context_window import evict_oldest
from askrag.agent.prompts import SYSTEM_PROMPT, fence
from askrag.config import Settings, get_settings
from askrag.tools import registry
from askrag.traces import ToolCallRecord


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
    `sse_events.py` and wiring an event stream to the frontend are #40's job;
    this is only the seam #40 will translate from."""

    kind: EventKind
    data: dict[str, Any]


def _noop_event(event: AgentEvent) -> None:
    return None


@dataclass(frozen=True)
class TurnResult:
    """One user-message turn's outcome — what a caller (#40's chat route, or
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
            result_blocks.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": error, "is_error": True}
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
        records.append(ToolCallRecord(name=name, args=args, ok=True))
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
    # a cache-read token counts as "used".
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


def _print_event(event: AgentEvent) -> None:
    if event.kind is EventKind.TOOL_CALL:
        print(f"  -> {event.data['name']}({event.data['args']})", file=sys.stderr)
    elif event.kind is EventKind.TOOL_RESULT:
        status = "ok" if event.data["ok"] else f"error: {event.data.get('error')}"
        print(f"     {status}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Cheap-first live smoke (owner directive 2026-07-06): set
    `ASKRAG_AGENT_API_BASE_URL` + `OPENROUTER_API_KEY` to validate the loop
    end-to-end against `smoke_model` before spending on Haiku; with neither
    set, this hits real Anthropic/Haiku instead. Cost is reported at Haiku's
    configured price regardless of which model actually served the call — the
    smoke validates plumbing, not billing (config.py `agent_usd_per_mtok_*`).
    Usage: uv run python -m askrag.agent.loop "question"
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("question", help="a question to ask the agent")
    args = parser.parse_args(argv)

    settings = get_settings()
    telemetry.init(settings)
    try:
        result = run_turn(
            [],
            args.question,
            session_id="smoke",
            ip="127.0.0.1",
            client=anthropic_client_from_settings(settings),
            settings=settings,
            on_event=_print_event,
        )
        print(result.text)
        print(
            f"\n[{result.stop_reason.value}, {len(result.tool_calls)} tool call(s), "
            f"{result.tokens_in}+{result.tokens_out} tokens, ~${result.cost_usd:.4f} "
            "(Haiku pricing, approximate on the smoke model)]",
            file=sys.stderr,
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
