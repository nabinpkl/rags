"""POST /api/chat (#30): the loop goes online. Budget gate FIRST (D11's
pre-flight read), then branch on its verdict — DENY is a plain HTTP error
(no stream to close), REPLAY and ALLOW both stream `sse_events` over SSE
through the identical wire shape (spec §4c: replay reproduces a live turn
"through the same endpoint shape"). `run_turn` (askrag/agent/loop.py) does
the per-message caps and persists its own trace; this route persists
nothing itself — that division of labor is unchanged from #21/#23.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import anyio
import anyio.from_thread
import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from askrag import db, traces
from askrag.agent import budgets
from askrag.agent.loop import (
    AgentEvent,
    EventKind,
    ModelClient,
    TurnResult,
    anthropic_client_from_settings,
    run_turn,
)
from askrag.api import sse_events
from askrag.api.replay import replay_events
from askrag.api.routes_landing import find_foundation, scope_paper_ids
from askrag.api.session_store import SessionStore
from askrag.config import Settings, get_settings

router = APIRouter()
_logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    # A landing-page claim to answer within, e.g. "1707.06347". The route
    # resolves it to that claim's INDEXED papers and binds the result into
    # tool dispatch, so the model receives a scope it cannot widen (§5/§6).
    # An unknown id is a 404, never a silently unscoped turn.
    foundation_id: str | None = None


def get_model_client(settings: Settings = Depends(get_settings)) -> ModelClient:
    """The provider seam (D2). Tests override this dependency with a
    scripted fake via `app.dependency_overrides` — no real API call ever
    runs in a test (house rule)."""
    return anthropic_client_from_settings(settings)


def get_session_store(request: Request) -> SessionStore:
    """The live-session store lives on `app.state` (one instance per
    process, minted in `app.py`'s lifespan) — not per-request state."""
    return request.app.state.session_store


def _client_ip(request: Request) -> str:
    # No reverse-proxy trust chain configured yet (Cloudflare/Caddy land at
    # deploy, D13): request.client is the direct peer. Revisit once a
    # trusted X-Forwarded-For source exists in front of this process.
    return request.client.host if request.client is not None else "unknown"


def _choose_showcase(pool: list[traces.Run], session_id: str) -> traces.Run:
    # Stable for one session within this process's lifetime, no RNG needed:
    # spreads visitors across the showcase pool. Python's str hash is
    # randomized per process start (PYTHONHASHSEED), so which pool slot a
    # given session lands on can shift across restarts — harmless, since
    # nothing depends on a session mapping to the same showcase forever.
    return pool[hash(session_id) % len(pool)]


async def _stream_replay(run: traces.Run) -> AsyncIterator[dict[str, Any]]:
    for event in replay_events(run):
        yield {"data": json.dumps(event)}


@dataclass
class _TurnOutcome:
    """Mutable box `on_event` and the worker-thread task write into, since a
    plain closure variable can't be reassigned from a nested function
    without `nonlocal` gymnastics across two callbacks."""

    result: TurnResult | None = None
    error: BaseException | None = None


async def _stream_live_turn(
    *,
    messages: list[Any],
    question: str,
    session_id: str,
    ip: str,
    client: ModelClient,
    settings: Settings,
    session_store: SessionStore,
    scope: tuple[str, ...] | None = None,
    scope_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """The sync-loop -> async-SSE bridge (the load-bearing piece of this
    route). `run_turn` is synchronous and blocking (sync SQLite + model
    client), so it runs in a worker thread (`anyio.to_thread.run_sync`); its
    `on_event` callback — itself executing in that thread — hands each event
    back across the thread boundary via an anyio memory stream
    (`anyio.from_thread.run`), and this generator drains the receive side,
    yielding SSE data AS THE EVENTS HAPPEN rather than buffering the whole
    turn and dumping it at the end.
    """
    send, receive = anyio.create_memory_object_stream[dict[str, Any]](max_buffer_size=64)
    outcome = _TurnOutcome()

    def on_event(event: AgentEvent) -> None:
        if event.kind is EventKind.DONE:
            # The route emits the terminal `done` event itself, from the
            # returned TurnResult, alongside `cost` (which has no AgentEvent
            # counterpart at all) — forwarding the loop's own internal DONE
            # here too would double-emit it out of order (before `cost`).
            return
        sse = sse_events.translate(event)
        if sse is None:
            return
        payload = {"data": json.dumps(sse_events.serialize(sse))}
        try:
            anyio.from_thread.run(send.send, payload)
        except anyio.BrokenResourceError:
            pass  # receiver already gone (client disconnected mid-turn)

    async def run_and_close() -> None:
        try:
            outcome.result = await anyio.to_thread.run_sync(
                lambda: run_turn(
                    messages,
                    question,
                    session_id=session_id,
                    ip=ip,
                    client=client,
                    settings=settings,
                    on_event=on_event,
                    scope=scope,
                )
            )
        except BaseException as exc:  # noqa: BLE001 — any loop failure still closes
            # the stream with a terminal event; never leave it hanging or
            # silently truncated. Logged here too (§ fail loud) — the SSE
            # terminal event tells the client the turn died, not why.
            _logger.error("askrag.api.chat: live turn failed", exc_info=exc)
            outcome.error = exc
        finally:
            await send.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_and_close)
        try:
            async with receive:
                async for payload in receive:
                    yield payload
        finally:
            # Reached on normal completion (harmless: run_and_close is
            # already done by then) AND on client disconnect / early
            # generator close. This does NOT abort the worker thread:
            # `run_sync` above has no `abandon_on_cancel=True` (anyio's
            # default is False), so cancelling the scope only stops event
            # delivery (send.send raises BrokenResourceError, swallowed in
            # on_event) while run_turn's synchronous while-loop keeps
            # running to max_tool_steps_per_message and still persists its
            # trace. A disconnected turn spends its full step-cap budget,
            # not a truncated one — the accepted-and-bounded overshoot from
            # the 2026-07-05 budget decision. True mid-turn abort isn't
            # reachable while run_turn is a sync loop with no cancellation
            # check; abandon_on_cancel=True wouldn't help either, since the
            # detached thread would still run to completion.
            tg.cancel_scope.cancel()

    if outcome.error is not None:
        yield {"data": json.dumps({"type": "done", "stop_reason": "error", "run_id": ""})}
        return

    result = outcome.result
    assert result is not None  # by construction: run_and_close sets one or the other
    session_store.save(session_id, result.messages, scope_key)
    yield {"data": json.dumps(sse_events.serialize(sse_events.cost_event(result)))}
    yield {"data": json.dumps(sse_events.serialize(sse_events.done_event(result)))}


def _resolve_scope(foundation_id: str | None, settings: Settings) -> tuple[str, ...] | None:
    """A landing-page claim -> the indexed papers a turn may be answered from.

    Resolved HERE, from corpus.db, rather than accepted as a client-supplied
    id list: a scope a caller can write is not a scope. An unknown foundation
    is a 404 — quietly running the turn unscoped would answer a question the
    user framed as being about one claim using the whole corpus.
    """
    if foundation_id is None:
        return None
    conn = db.connect_corpus(settings.corpus_db_path)
    try:
        if find_foundation(conn, foundation_id) is None:
            raise HTTPException(status_code=404, detail=f"no cited work with id {foundation_id!r}")
        scope = scope_paper_ids(conn, foundation_id)
    finally:
        conn.close()
    if not scope:
        # An empty scope retrieves nothing by construction, so the turn would
        # spend real money against the D11 caps to produce "I found nothing".
        # Refusing pre-flight is the same posture as the budget gate below:
        # say why, before spending.
        raise HTTPException(
            status_code=422,
            detail=f"no indexed papers for {foundation_id!r} — nothing to answer from",
        )
    return scope


@router.post("/api/chat", response_model=None)
async def post_chat(
    body: ChatRequest,
    request: Request,
    client: ModelClient = Depends(get_model_client),
    session_store: SessionStore = Depends(get_session_store),
    settings: Settings = Depends(get_settings),
) -> JSONResponse | EventSourceResponse:
    session_id = body.session_id or uuid4().hex
    ip = _client_ip(request)

    decision = budgets.check(session_id, ip, settings=settings)

    if decision.verdict is budgets.Verdict.DENY:
        # A pre-flight rejection is a plain HTTP error, not a stream — the
        # SSE vocabulary stays untouched by the reject path.
        return JSONResponse(
            status_code=429,
            content={"reason": decision.reason},
            headers={"X-AskRAG-Session-Id": session_id},
        )

    if decision.verdict is budgets.Verdict.REPLAY:
        pool = traces.get_showcase_traces(settings=settings)
        if not pool:
            raise HTTPException(
                status_code=503, detail="Replay unavailable: no showcase traces recorded yet."
            )
        run = _choose_showcase(pool, session_id)
        return EventSourceResponse(
            _stream_replay(run),
            headers={
                "X-AskRAG-Mode": "replay",
                # HTTP header values are Latin-1-only; budgets.py's reasons
                # are plain English but not ASCII-only (e.g. an em dash) —
                # percent-encode so the header never breaks, frontend
                # decodes with decodeURIComponent().
                "X-AskRAG-Reason": quote(decision.reason),
                "X-AskRAG-Session-Id": session_id,
            },
        )

    scope = _resolve_scope(body.foundation_id, settings)
    messages = session_store.get_or_create(session_id, body.foundation_id)
    return EventSourceResponse(
        _stream_live_turn(
            messages=messages,
            question=body.question,
            session_id=session_id,
            ip=ip,
            client=client,
            settings=settings,
            session_store=session_store,
            scope=scope,
            scope_key=body.foundation_id,
        ),
        headers={"X-AskRAG-Session-Id": session_id},
    )
