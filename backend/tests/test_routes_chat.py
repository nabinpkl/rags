"""Tests for askrag.api.routes_chat — POST /api/chat: the budget gate
(Deny/Replay/Allow), the live sync-loop -> async-SSE bridge, and replay
mode. No API ever runs (house rule): the ModelClient is a scripted fake
wired in via `app.dependency_overrides`."""

import json
import threading
import time
from dataclasses import dataclass

import anyio
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from askrag import traces
from askrag.api import routes_chat
from askrag.api.session_store import SessionStore
from askrag.api.turn_slots import TurnSlots
from askrag.config import Settings, get_settings
from askrag.tools import registry

# --- fakes: the ModelClient seam, satisfied without any network call --------


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class ScriptedModelClient:
    """Returns canned responses in order (askrag/agent/loop.py's own test
    pattern, tests/test_loop.py)."""

    def __init__(self, responses):
        self._responses = list(responses)

    def create(self, *, system, messages, tools):
        return self._responses.pop(0)


class StubResult:
    def __init__(self, payload):
        self._payload = payload

    def to_model_payload(self):
        return self._payload


def tool_use_response(call_id, name="query_metadata", args=None):
    return FakeResponse(
        content=[FakeToolUseBlock(id=call_id, name=name, input=args or {"op": "corpus_stats"})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )


def text_response(text):
    return FakeResponse(
        content=[FakeTextBlock(text=text)],
        stop_reason="end_turn",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )


def make_settings(tmp_path, **overrides):
    return Settings(traces_db_path=tmp_path / "traces.db", _env_file=None, **overrides)  # ty: ignore[unknown-argument]


def make_app(*, settings, client) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_chat.router)
    app.state.session_store = SessionStore(settings=settings)
    app.state.turn_slots = TurnSlots(settings.chat_max_concurrent_turns)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[routes_chat.get_model_client] = lambda: client
    return app


def _sse_data_lines(resp) -> list[dict]:
    return [
        json.loads(line[len("data: ") :]) for line in resp.iter_lines() if line.startswith("data: ")
    ]


# --- ALLOW: streams events in order, closes with cost + done ---------------


def test_allow_streams_events_in_order_and_closes_with_cost_and_done(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry, "dispatch", lambda name, args, *, scope=None: StubResult({"n_papers": 6460})
    )
    settings = make_settings(tmp_path)
    client = ScriptedModelClient([tool_use_response("t1"), text_response("There are 6460 papers.")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "how many papers?"}) as resp:
            assert resp.status_code == 200
            assert resp.headers["x-askrag-session-id"]
            events = _sse_data_lines(resp)

    assert [e["type"] for e in events] == [
        "tool_call",
        "tool_result_summary",
        "text",
        "cost",
        "done",
    ]
    assert events[0] == {
        "type": "tool_call",
        "name": "query_metadata",
        "args": {"op": "corpus_stats"},
    }
    assert events[2] == {"type": "text", "text": "There are 6460 papers."}
    assert events[-1]["stop_reason"] == "end_turn"
    assert events[-1]["run_id"]


def test_allow_mints_a_session_id_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)
    client = ScriptedModelClient([text_response("hi")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "hello"}) as resp:
            session_id = resp.headers["x-askrag-session-id"]
            list(resp.iter_lines())  # drain
    assert session_id


def test_allow_persists_a_trace_with_question_and_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)
    client = ScriptedModelClient([text_response("the answer")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        with tc.stream(
            "POST", "/api/chat", json={"question": "a question", "session_id": "s1"}
        ) as resp:
            events = _sse_data_lines(resp)

    run_id = events[-1]["run_id"]
    run = traces.get_run(run_id, settings=settings)
    assert run is not None
    assert run.question == "a question"
    assert run.answer_text == "the answer"
    assert run.showcase is False


# --- DENY: 429 with a displayable reason, no stream -------------------------


def test_deny_returns_429_with_reason(tmp_path):
    settings = make_settings(tmp_path, session_message_cap=0)
    app = make_app(settings=settings, client=ScriptedModelClient([]))

    with TestClient(app) as tc:
        resp = tc.post("/api/chat", json={"question": "hi", "session_id": "s1"})

    assert resp.status_code == 429
    body = resp.json()
    assert "reason" in body and body["reason"]


# --- REPLAY: streams a seeded showcase trace through the same shape --------


def test_replay_streams_a_seeded_showcase_trace_with_mode_header(tmp_path):
    settings = make_settings(tmp_path, global_daily_spend_cap_usd=0.01)
    traces.record_run(
        session_id="demo",
        ip="127.0.0.1",
        question="what is cot?",
        answer_text="Chain of thought is a prompting technique.",
        tokens_in=100,
        tokens_out=20,
        cost_usd=0.02,  # trips the 0.01 global cap
        latency_ms=10.0,
        tool_calls=[traces.ToolCallRecord(name="search_corpus", args={"query": "cot"}, ok=True)],
        showcase=True,
        settings=settings,
    )
    app = make_app(settings=settings, client=ScriptedModelClient([]))

    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "what is cot?"}) as resp:
            assert resp.status_code == 200
            assert resp.headers["x-askrag-mode"] == "replay"
            assert resp.headers["x-askrag-reason"]
            events = _sse_data_lines(resp)

    assert [e["type"] for e in events] == [
        "tool_call",
        "tool_result_summary",
        "text",
        "cost",
        "done",
    ]
    assert events[2] == {"type": "text", "text": "Chain of thought is a prompting technique."}


def test_replay_with_no_showcase_pool_returns_503(tmp_path):
    settings = make_settings(tmp_path, global_daily_spend_cap_usd=0.0)
    app = make_app(settings=settings, client=ScriptedModelClient([]))

    with TestClient(app) as tc:
        resp = tc.post("/api/chat", json={"question": "q", "session_id": "s1"})

    assert resp.status_code == 503


# --- the load-bearing bridge: live stream is incremental, not buffered ----


def test_live_stream_is_incremental_not_a_buffered_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)
    release = threading.Event()

    class BlockingSecondCallClient:
        def __init__(self):
            self.n_calls = 0

        def create(self, *, system, messages, tools):
            self.n_calls += 1
            if self.n_calls == 1:
                return tool_use_response("t1")
            # The second model call blocks until the test has already read
            # the first round's SSE events off the wire — bounded by a 5s
            # watchdog so a broken (buffered) implementation fails fast
            # instead of hanging the suite.
            release.wait(timeout=5)
            return text_response("done")

    app = make_app(settings=settings, client=BlockingSecondCallClient())

    seen: list[dict] = []
    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "q"}) as resp:
            lines = resp.iter_lines()
            started = time.monotonic()
            for line in lines:
                if not line.startswith("data: "):
                    continue
                seen.append(json.loads(line[len("data: ") :]))
                if len(seen) == 2:
                    break
            elapsed = time.monotonic() - started
            release.set()
            for line in lines:
                if line.startswith("data: "):
                    seen.append(json.loads(line[len("data: ") :]))

    assert [e["type"] for e in seen[:2]] == ["tool_call", "tool_result_summary"]
    # Arrived well inside the 5s watchdog window: proof they were flushed as
    # they happened, not withheld until the whole turn (and the blocked
    # second call) finished.
    assert elapsed < 2.0
    assert seen[-1]["type"] == "done"


def test_live_stream_surfaces_a_terminal_event_on_loop_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)

    class ExplodingClient:
        def create(self, *, system, messages, tools):
            raise RuntimeError("boom")

    app = make_app(settings=settings, client=ExplodingClient())

    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "q"}) as resp:
            assert resp.status_code == 200
            events = _sse_data_lines(resp)

    assert events == [{"type": "done", "stop_reason": "error", "run_id": ""}]


# --- SCOPE: a landing-page claim narrows the turn, server-side -------------


def _scoped_corpus(tmp_path):
    """A corpus where 2401.00001 cites PPO and is indexed; 2401.00002 is not."""
    from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
    from askrag.ingest.resolve_cited_works import CitedWorkRow

    def paper(arxiv_id):
        return PaperRow(
            arxiv_id=arxiv_id,
            title="t",
            authors="a",
            abstract="x",
            categories="cs.LG",
            published="2024-01-01",
            version="v1",
            license=None,
            venue=None,
            authority=None,
            niche_idf=None,
            author_novelty=None,
            revisions=None,
            venue_rigor=None,
        )

    _write_corpus_db(
        tmp_path / "corpus.db",
        [paper("2401.00001"), paper("2401.00002")],
        [ChunkRow("2401.00001#0", "2401.00001", "__paper__", 1, 1, "grpo", 2)],
        [CitedWorkRow("1707.06347", "PPO", "J. S.", "cs.LG", 2017, "v2")],
        [("2401.00001", "1707.06347"), ("2401.00002", "1707.06347")],
    )
    return make_settings(tmp_path, corpus_dir=tmp_path)


def test_a_foundation_id_scopes_the_turn_to_its_indexed_citers(tmp_path, monkeypatch):
    """The route resolves the scope; the model never writes it (§5/§6).

    Both papers cite PPO, but only 2401.00001 is indexed — the agent is handed
    the papers it can actually read, and cannot reach past them.
    """
    seen: list[object] = []

    def fake_dispatch(name, args, *, scope=None):
        seen.append(scope)
        return StubResult({"ok": True})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)
    settings = _scoped_corpus(tmp_path)
    client = ScriptedModelClient([tool_use_response("t1"), text_response("answered")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        with tc.stream(
            "POST",
            "/api/chat",
            json={"question": "what do they report?", "foundation_id": "1707.06347"},
        ) as resp:
            assert resp.status_code == 200
            _sse_data_lines(resp)

    assert seen == [("2401.00001",)]


def test_an_unscoped_turn_still_passes_no_scope(tmp_path, monkeypatch):
    seen: list[object] = []

    def fake_dispatch(name, args, *, scope=None):
        seen.append(scope)
        return StubResult({"ok": True})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)
    settings = _scoped_corpus(tmp_path)
    client = ScriptedModelClient([tool_use_response("t1"), text_response("answered")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "anything"}) as resp:
            _sse_data_lines(resp)

    assert seen == [None]


def test_an_unknown_foundation_is_404_not_a_silently_unscoped_turn(tmp_path):
    """Falling back to the whole corpus would answer a different question."""
    settings = _scoped_corpus(tmp_path)
    client = ScriptedModelClient([text_response("answered")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        resp = tc.post("/api/chat", json={"question": "q", "foundation_id": "9999.99999"})

    assert resp.status_code == 404


def test_a_claim_with_no_indexed_papers_is_refused_before_spending(tmp_path):
    """An empty scope retrieves nothing by construction.

    Running the turn anyway would spend against the D11 caps to produce "I
    found nothing" — refusing pre-flight is the budget gate's own posture.
    """
    from askrag.ingest.build_indexes import PaperRow, _write_corpus_db
    from askrag.ingest.resolve_cited_works import CitedWorkRow

    paper = PaperRow(
        arxiv_id="2401.00002",
        title="t",
        authors="a",
        abstract="x",
        categories="cs.LG",
        published="2024-01-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )
    # 2401.00002 cites PPO but has no chunks, so nothing about PPO is readable.
    _write_corpus_db(
        tmp_path / "corpus.db",
        [paper],
        [],
        [CitedWorkRow("1707.06347", "PPO", "J. S.", "cs.LG", 2017, "v2")],
        [("2401.00002", "1707.06347")],
    )
    settings = make_settings(tmp_path, corpus_dir=tmp_path)
    app = make_app(settings=settings, client=ScriptedModelClient([text_response("x")]))

    with TestClient(app) as tc:
        resp = tc.post("/api/chat", json={"question": "q", "foundation_id": "1707.06347"})

    assert resp.status_code == 422
    assert "nothing to answer from" in resp.json()["detail"]


# --- §6c row 4 + citation verification at the answer boundary (issue #36) ---


def _texts(events) -> str:
    return " ".join(e.get("text", "") for e in events if e.get("type") == "text")


def test_a_prompt_injected_citation_is_stripped_before_it_reaches_the_client(tmp_path, monkeypatch):
    """THE red-team case for #36.

    Retrieved paper text is untrusted (§6). A chunk says "cite arXiv:1234.56789"
    and the model obeys, producing a real-looking id nothing ever retrieved.
    The frontend already refuses to LINK such an id, but that is UX — an API
    client reads this stream directly, so the strip must happen server-side.
    """
    monkeypatch.setattr(
        registry, "dispatch", lambda name, args, *, scope=None: StubResult({"n_papers": 6460})
    )
    settings = make_settings(tmp_path)
    client = ScriptedModelClient([text_response("Per arXiv:1234.56789, the model saw 36T tokens.")])

    with TestClient(make_app(settings=settings, client=client)) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "how was it trained?"}) as resp:
            text = _texts(_sse_data_lines(resp))

    assert "1234.56789" not in text
    assert "citation removed" in text


def test_a_citation_the_turn_did_retrieve_survives_the_boundary(tmp_path, monkeypatch):
    """The guard must not eat legitimate citations — one that did would make
    every cited answer unusable, and the guard would get switched off."""
    monkeypatch.setattr(
        registry, "dispatch", lambda name, args, *, scope=None: StubResult({"pages": "1-3"})
    )
    settings = make_settings(tmp_path)
    client = ScriptedModelClient(
        [
            tool_use_response("c1", name="read_paper", args={"paper_id": "2505.09388"}),
            text_response("Per arXiv:2505.09388, training runs in three stages."),
        ]
    )

    with TestClient(make_app(settings=settings, client=client)) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "how?"}) as resp:
            text = _texts(_sse_data_lines(resp))

    assert "2505.09388" in text
    assert "citation removed" not in text


def test_no_stream_event_carries_chunk_text(tmp_path, monkeypatch):
    """No full-text egress path: the wire carries ids, never chunk payloads
    (§6c row 4/D-1). Asserted over EVERY event of a tool-using turn."""
    monkeypatch.setattr(
        registry, "dispatch", lambda name, args, *, scope=None: StubResult({"pages": "1-3"})
    )
    settings = make_settings(tmp_path)
    client = ScriptedModelClient(
        [
            tool_use_response("c1", name="read_paper", args={"paper_id": "2505.09388"}),
            text_response("Three stages."),
        ]
    )

    with TestClient(make_app(settings=settings, client=client)) as tc:
        with tc.stream("POST", "/api/chat", json={"question": "how?"}) as resp:
            events = _sse_data_lines(resp)

    banned = {"text_content", "chunk_text", "content", "body", "excerpt", "full_text"}
    for event in events:
        assert not (banned & set(event)), f"{event.get('type')} carries a text payload"
        for citation in event.get("citations", []):
            assert set(citation) == {"paper_id", "chunk_ids"}


# --- request bounds, client address, concurrent turns -----------------------


def test_an_empty_question_is_refused_before_any_model_call(tmp_path):
    settings = make_settings(tmp_path)
    app = make_app(settings=settings, client=ScriptedModelClient([]))
    with TestClient(app) as tc:
        assert tc.post("/api/chat", json={"question": ""}).status_code == 422


def test_a_question_over_the_configured_length_is_refused(tmp_path):
    settings = make_settings(tmp_path, chat_question_max_chars=10)
    app = make_app(settings=settings, client=ScriptedModelClient([]))
    with TestClient(app) as tc:
        resp = tc.post("/api/chat", json={"question": "x" * 11})
    assert resp.status_code == 422
    assert traces.spend_today(settings=settings) == 0


def test_an_oversized_or_unprintable_session_id_is_refused(tmp_path):
    settings = make_settings(tmp_path)
    app = make_app(settings=settings, client=ScriptedModelClient([]))
    with TestClient(app) as tc:
        long_id = tc.post("/api/chat", json={"question": "hi", "session_id": "a" * 65})
        newline = tc.post("/api/chat", json={"question": "hi", "session_id": "a\nb"})
    assert long_id.status_code == 422
    assert newline.status_code == 422


def _ask(tc, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    with tc.stream("POST", "/api/chat", json={"question": "hi"}, headers=headers) as resp:
        list(resp.iter_lines())
        return resp


def test_behind_a_trusted_proxy_each_visitor_gets_their_own_ip_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    # TestClient's peer is "testclient", not an address; trust it by name the
    # way the compose subnet is trusted in deploy.
    monkeypatch.setattr(routes_chat, "client_ip", lambda peer, xff, trusted: xff or peer)
    # One turn costs 60 tokens at the table rate; a cap just under it means
    # the first turn from a network spends that network's day.
    settings = make_settings(tmp_path, ip_daily_spend_cap_usd=1e-6)
    client = ScriptedModelClient([text_response("a"), text_response("b")])
    app = make_app(settings=settings, client=client)

    with TestClient(app) as tc:
        assert _ask(tc, "100.71.2.3").status_code == 200
        assert _ask(tc, "100.71.2.3").status_code == 429
        assert _ask(tc, "100.80.4.5").status_code == 200


def test_the_route_reads_forwarded_for_only_from_trusted_peers(tmp_path):
    settings = make_settings(tmp_path, trusted_proxy_cidrs=["10.120.0.0/24"])

    def request(peer, xff):
        return Request(
            {
                "type": "http",
                "client": (peer, 40000),
                "headers": [(b"x-forwarded-for", xff.encode())],
            }
        )

    via_caddy = request("10.120.0.3", "9.9.9.9, 100.71.2.3, 10.120.0.1")
    direct = request("203.0.113.9", "100.71.2.3")
    assert routes_chat._client_ip(via_caddy, settings) == "100.71.2.3"
    assert routes_chat._client_ip(direct, settings) == "203.0.113.9"


def test_when_every_turn_slot_is_taken_the_route_answers_503(tmp_path):
    settings = make_settings(tmp_path, chat_max_concurrent_turns=1)
    app = make_app(settings=settings, client=ScriptedModelClient([]))
    with TestClient(app) as tc:
        assert app.state.turn_slots.try_acquire()
        resp = tc.post("/api/chat", json={"question": "hi"})
    assert resp.status_code == 503
    assert resp.headers["retry-after"]
    assert resp.json()["reason"]


def test_a_finished_turn_gives_its_slot_back(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path, chat_max_concurrent_turns=1)
    client = ScriptedModelClient([text_response("a"), text_response("b")])
    app = make_app(settings=settings, client=client)
    with TestClient(app) as tc:
        assert _ask(tc).status_code == 200
        assert app.state.turn_slots.in_use == 0
        assert _ask(tc).status_code == 200


def test_a_failed_turn_gives_its_slot_back(tmp_path):
    class Boom:
        def create(self, *, system, messages, tools):
            raise RuntimeError("provider down")

    settings = make_settings(tmp_path, chat_max_concurrent_turns=1)
    app = make_app(settings=settings, client=Boom())
    with TestClient(app) as tc:
        _ask(tc)
        assert app.state.turn_slots.in_use == 0


def test_a_turn_racing_past_the_full_check_ends_with_an_error_event(tmp_path):
    # The route saw a free slot; another turn took it before this one's
    # stream started. The generator's own acquire is the one that holds.
    settings = make_settings(tmp_path, chat_max_concurrent_turns=1)
    slots = TurnSlots(1)
    events = []

    async def drain():
        assert slots.try_acquire()
        async for payload in routes_chat._stream_live_turn(
            messages=[],
            question="hi",
            session_id="s1",
            ip="1.2.3.4",
            client=ScriptedModelClient([]),
            settings=settings,
            session_store=SessionStore(settings=settings),
            slots=slots,
        ):
            events.append(json.loads(payload["data"]))

    anyio.run(drain)
    assert events == [{"type": "done", "stop_reason": "error", "run_id": ""}]
    assert slots.in_use == 1  # the other turn's slot, untouched
