"""Tests for askrag.agent.loop against a SCRIPTED FAKE model — no API, ever
(house rule). Covers: tool dispatch round-trips through the registry;
step-cap enforcement (stops at max_tool_steps_per_message, forced final turn
fires); token-budget stop; fence present and labeled on every tool result
re-entering the model; unknown-tool handling; the forced final turn never
offers tools."""

from dataclasses import dataclass

import pytest

from askrag import traces
from askrag.agent import loop, prompts
from askrag.config import Settings
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
    """Returns canned responses in order; records every call's `tools` arg so
    tests can assert the forced final turn removes tools."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.tools_per_call: list[object] = []

    def create(self, *, system, messages, tools):
        self.tools_per_call.append(tools)
        return self._responses.pop(0)


class StubResult:
    def __init__(self, payload):
        self._payload = payload

    def to_model_payload(self):
        return self._payload


def tool_use_response(call_id, name="query_metadata", args=None, tokens=(50, 10)):
    return FakeResponse(
        content=[FakeToolUseBlock(id=call_id, name=name, input=args or {"op": "corpus_stats"})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=tokens[0], output_tokens=tokens[1]),
    )


def text_response(text, tokens=(50, 10)):
    return FakeResponse(
        content=[FakeTextBlock(text=text)],
        stop_reason="end_turn",
        usage=FakeUsage(input_tokens=tokens[0], output_tokens=tokens[1]),
    )


def make_settings(tmp_path, **overrides):
    return Settings(traces_db_path=tmp_path / "traces.db", _env_file=None, **overrides)  # ty: ignore[unknown-argument]


# --- tool dispatch round-trips through the registry -------------------------


def test_tool_dispatch_round_trips_through_registry(tmp_path, monkeypatch):
    calls = []

    def fake_dispatch(name, args, *, scope=None):
        calls.append((name, args))
        return StubResult({"n_papers": 6460})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)
    client = ScriptedModelClient(
        [
            tool_use_response("t1", args={"op": "corpus_stats"}),
            text_response("There are 6460 papers."),
        ]
    )
    settings = make_settings(tmp_path)

    result = loop.run_turn(
        [], "how many papers?", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert calls == [("query_metadata", {"op": "corpus_stats"})]
    assert result.stop_reason is loop.StopReason.END_TURN
    assert result.text == "There are 6460 papers."
    assert result.tool_calls == (
        traces.ToolCallRecord(name="query_metadata", args={"op": "corpus_stats"}, ok=True),
    )


@dataclass
class FakeScoredChunk:
    paper_id: str
    chunk_id: str


class StubSearchCorpusResult:
    """Mimics SearchCorpusResult's real shape (`.chunks` of paper_id/chunk_id
    objects) — `_citations_of` reads exactly that, duck-typed (issue #27)."""

    def __init__(self, chunks):
        self.chunks = chunks

    def to_model_payload(self):
        return {"chunks": [{"paper_id": c.paper_id, "chunk_id": c.chunk_id} for c in self.chunks]}


def test_search_corpus_result_ids_land_in_the_tool_call_record_as_citations(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry,
        "dispatch",
        lambda name, args, *, scope=None: StubSearchCorpusResult(
            [
                FakeScoredChunk(paper_id="2401.00001", chunk_id="2401.00001#0"),
                FakeScoredChunk(paper_id="2401.00001", chunk_id="2401.00001#1"),
                FakeScoredChunk(paper_id="2401.00002", chunk_id="2401.00002#0"),
            ]
        ),
    )
    client = ScriptedModelClient(
        [tool_use_response("t1", name="search_corpus", args={"query": "cot"}), text_response("ok")]
    )
    settings = make_settings(tmp_path)

    result = loop.run_turn(
        [], "what is cot?", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert result.tool_calls[0].citations == (
        traces.Citation(paper_id="2401.00001", chunk_id="2401.00001#0"),
        traces.Citation(paper_id="2401.00001", chunk_id="2401.00001#1"),
        traces.Citation(paper_id="2401.00002", chunk_id="2401.00002#0"),
    )


def test_non_search_corpus_tool_calls_carry_no_citations(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry, "dispatch", lambda name, args, *, scope=None: StubResult({"n_papers": 6460})
    )
    client = ScriptedModelClient([tool_use_response("t1"), text_response("ok")])
    settings = make_settings(tmp_path)

    result = loop.run_turn(
        [], "how many papers?", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert result.tool_calls[0].citations == ()


def test_fence_present_and_labeled_on_every_tool_result(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry,
        "dispatch",
        lambda name, args, *, scope=None: StubResult({"paper_id": args["paper_id"]}),
    )
    client = ScriptedModelClient(
        [
            FakeResponse(
                content=[
                    FakeToolUseBlock(id="a", name="read_paper", input={"paper_id": "2401.00001"}),
                    FakeToolUseBlock(id="b", name="read_paper", input={"paper_id": "2401.00002"}),
                ],
                stop_reason="tool_use",
                usage=FakeUsage(input_tokens=50, output_tokens=10),
            ),
            text_response("done"),
        ]
    )
    settings = make_settings(tmp_path)

    result = loop.run_turn(
        [], "compare two papers", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    tool_result_message = result.messages[2]
    fenced_contents = [block["content"] for block in tool_result_message["content"]]
    assert len(fenced_contents) == 2
    for content in fenced_contents:
        assert content.startswith(f"<{prompts.FENCE_TAG}>")
        assert content.endswith(f"</{prompts.FENCE_TAG}>")


# --- unknown-tool handling ----------------------------------------------------


def test_unknown_tool_becomes_an_error_tool_result_not_a_crash(tmp_path):
    # No monkeypatch: the real registry.dispatch already raises UnknownToolError
    # before touching any handler/DB (registry.py's own contract).
    client = ScriptedModelClient(
        [
            tool_use_response("t1", name="hack_the_mainframe", args={}),
            text_response("I can't do that, but here's what I can tell you."),
        ]
    )
    settings = make_settings(tmp_path)

    result = loop.run_turn(
        [], "hack the mainframe", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert len(result.tool_calls) == 1
    record = result.tool_calls[0]
    assert record.ok is False
    assert "hack_the_mainframe" in (record.error or "")

    tool_result_block = result.messages[2]["content"][0]
    assert tool_result_block["is_error"] is True
    # The error content is fenced exactly like a success result (§6: the
    # fence is total by construction, no unfenced model-facing content path).
    assert tool_result_block["content"].startswith(f"<{prompts.FENCE_TAG}>")
    assert tool_result_block["content"].endswith(f"</{prompts.FENCE_TAG}>")
    assert "hack_the_mainframe" in tool_result_block["content"]


# --- step-cap enforcement -----------------------------------------------------


def test_step_cap_enforcement_forces_a_final_synthesis_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)

    # The model keeps asking for one more tool call forever; the loop must
    # cut it off at max_tool_steps_per_message and force a synthesis turn.
    responses = [
        tool_use_response(f"t{i}") for i in range(1, settings.max_tool_steps_per_message + 2)
    ]
    responses.append(text_response("Here is a synthesis without further tools."))
    client = ScriptedModelClient(responses)

    result = loop.run_turn(
        [],
        "an unbounded multi-hop question",
        session_id="s1",
        ip="127.0.0.1",
        client=client,
        settings=settings,
    )

    assert result.stop_reason is loop.StopReason.STEP_CAP
    assert len(result.tool_calls) == settings.max_tool_steps_per_message
    assert result.text == "Here is a synthesis without further tools."
    # max_tool_steps_per_message dispatched rounds + the one blocked request's
    # own model call + the forced synthesis call.
    assert len(client.tools_per_call) == settings.max_tool_steps_per_message + 2
    # The forced final call must not offer tools — a stop-cap turn can't ask
    # the model for more of the thing that just got capped.
    assert client.tools_per_call[-1] is None

    # The dangling (blocked) tool_use got a stub tool_result, not silence —
    # the transcript stays API-valid for the forced call.
    stub_message = result.messages[-2]
    assert stub_message["role"] == "user"
    assert stub_message["content"][0]["content"] == "[not run: step/token budget reached]"


def test_the_forced_final_answer_reaches_the_reader(tmp_path, monkeypatch):
    # Regression: the forced synthesis set result.text but emitted no TEXT
    # event, so a capped turn's answer never reached the stream.
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path, max_tool_steps_per_message=1)
    client = ScriptedModelClient(
        [tool_use_response("t1"), tool_use_response("t2"), text_response("forced answer")]
    )
    events = []

    loop.run_turn(
        [],
        "q",
        session_id="s1",
        ip="127.0.0.1",
        client=client,
        settings=settings,
        on_event=events.append,
    )

    texts = [e for e in events if e.kind is loop.EventKind.TEXT]
    assert [e.data["text"] for e in texts] == ["forced answer"]
    # It carries the turn's tool calls, which answer_guard checks citations against.
    assert len(texts[0].data["tool_calls"]) == 1
    assert events[-1].kind is loop.EventKind.DONE


def test_a_forced_turn_with_no_text_keeps_the_last_answer_and_emits_nothing_new(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path, max_tool_steps_per_message=0)
    narrated = FakeResponse(
        content=[
            FakeTextBlock(text="let me look"),
            FakeToolUseBlock(id="t1", name="query_metadata", input={"op": "corpus_stats"}),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )
    silent = FakeResponse(content=[], stop_reason="end_turn", usage=FakeUsage(50, 10))
    events = []

    result = loop.run_turn(
        [],
        "q",
        session_id="s1",
        ip="127.0.0.1",
        client=ScriptedModelClient([narrated, silent]),
        settings=settings,
        on_event=events.append,
    )

    assert result.text == "let me look"
    assert [e.data["text"] for e in events if e.kind is loop.EventKind.TEXT] == ["let me look"]


# --- token-budget stop ---------------------------------------------------------


def test_token_budget_stop_forces_a_final_synthesis_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path, message_token_budget=100)

    client = ScriptedModelClient(
        [
            tool_use_response("t1", tokens=(80, 10)),  # 90 total: under budget, continues
            tool_use_response("t2", tokens=(50, 10)),  # cumulative 150: over budget, stops
            text_response("Synthesis under the token budget cap."),
        ]
    )

    result = loop.run_turn(
        [],
        "a token-hungry question",
        session_id="s1",
        ip="127.0.0.1",
        client=client,
        settings=settings,
    )

    assert result.stop_reason is loop.StopReason.TOKEN_BUDGET
    assert len(result.tool_calls) == 1  # only the first round actually dispatched
    assert result.text == "Synthesis under the token budget cap."
    assert client.tools_per_call[-1] is None


# --- cost accounting -----------------------------------------------------------


def test_cost_and_traces_recorded_once_per_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)
    client = ScriptedModelClient(
        [
            tool_use_response("t1", tokens=(1000, 100)),
            text_response("final", tokens=(500, 50)),
        ]
    )

    result = loop.run_turn(
        [], "question", session_id="sess-x", ip="203.0.113.1", client=client, settings=settings
    )

    assert result.tokens_in == 1500
    assert result.tokens_out == 150
    expected_cost = (
        1500 / 1_000_000 * settings.agent_usd_per_mtok_in
        + 150 / 1_000_000 * settings.agent_usd_per_mtok_out
    )
    assert result.cost_usd == pytest.approx(expected_cost)

    run = traces.get_run(result.run_id, settings=settings)
    assert run is not None
    assert run.session_id == "sess-x"
    assert run.tokens_in == 1500
    assert run.tool_calls == result.tool_calls


def test_cache_read_tokens_count_toward_total_but_price_at_the_cache_rate(tmp_path, monkeypatch):
    # A response usage with cache_read_input_tokens set must still be counted
    # in tokens_in (it was real context the model read) while being billed at
    # agent_usd_per_mtok_cache_read, not the full input rate.
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path)
    client = ScriptedModelClient(
        [
            FakeResponse(
                content=[FakeTextBlock(text="answer")],
                stop_reason="end_turn",
                usage=FakeUsage(input_tokens=100, output_tokens=20, cache_read_input_tokens=900),
            ),
        ]
    )

    result = loop.run_turn(
        [], "question", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert result.tokens_in == 1000  # 100 fresh + 900 cache-read, not just the fresh 100
    expected_cost = (
        100 / 1_000_000 * settings.agent_usd_per_mtok_in
        + 20 / 1_000_000 * settings.agent_usd_per_mtok_out
        + 900 / 1_000_000 * settings.agent_usd_per_mtok_cache_read
    )
    assert result.cost_usd == pytest.approx(expected_cost)


def test_a_scoped_turn_passes_its_scope_to_every_tool_call(tmp_path, monkeypatch):
    """The scope reaches dispatch as a keyword, for the whole turn.

    A scope the model could omit by not writing an argument would be no scope
    at all — the loop supplies it on every call, whatever the model asked for.
    """
    seen: list[tuple[str, ...] | None] = []

    def fake_dispatch(name, args, *, scope=None):
        seen.append(scope)
        return StubResult({"ok": True})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)
    client = ScriptedModelClient(
        [
            tool_use_response("t1", name="read_paper", args={"paper_id": "2401.00001"}),
            tool_use_response("t2", name="query_metadata", args={"op": "corpus_stats"}),
            text_response("done"),
        ]
    )

    loop.run_turn(
        [],
        "what do they report?",
        session_id="s1",
        ip="127.0.0.1",
        client=client,
        settings=make_settings(tmp_path),
        scope=("2401.00001", "2401.00002"),
    )

    assert seen == [("2401.00001", "2401.00002"), ("2401.00001", "2401.00002")]


# --- denial-of-wallet bounds inside one turn --------------------------------


def test_one_response_runs_at_most_max_tool_calls_per_step(tmp_path, monkeypatch):
    calls = []

    def fake_dispatch(name, args, *, scope=None):
        calls.append(name)
        return StubResult({})

    monkeypatch.setattr(registry, "dispatch", fake_dispatch)
    burst = FakeResponse(
        content=[
            FakeToolUseBlock(id=f"t{i}", name="query_metadata", input={"op": "corpus_stats"})
            for i in range(6)
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )
    client = ScriptedModelClient([burst, text_response("done")])
    settings = make_settings(tmp_path, max_tool_calls_per_step=2)

    result = loop.run_turn(
        [], "q", session_id="s1", ip="127.0.0.1", client=client, settings=settings
    )

    assert len(calls) == 2
    results = result.messages[2]["content"]
    # Every tool_use still gets a result, in order, or the next call is invalid.
    assert [b["tool_use_id"] for b in results] == [f"t{i}" for i in range(6)]
    refused = [b for b in results if b.get("is_error")]
    assert len(refused) == 4
    assert all("not run" in b["content"] for b in refused)


def test_refused_tool_calls_emit_no_events(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    burst = FakeResponse(
        content=[
            FakeToolUseBlock(id=f"t{i}", name="drive_ui", input={"action": "set_filters"})
            for i in range(3)
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )
    events = []
    loop.run_turn(
        [],
        "q",
        session_id="s1",
        ip="127.0.0.1",
        client=ScriptedModelClient([burst, text_response("done")]),
        settings=make_settings(tmp_path, max_tool_calls_per_step=1),
        on_event=events.append,
    )
    assert sum(e.kind is loop.EventKind.TOOL_CALL for e in events) == 1


class FailingOnCall:
    """Answers with a tool call until call `n`, which raises."""

    def __init__(self, n):
        self.n, self.calls = n, 0

    def create(self, *, system, messages, tools):
        self.calls += 1
        if self.calls == self.n:
            raise RuntimeError("provider overloaded")
        return tool_use_response(f"t{self.calls}", tokens=(1_000_000, 0))


def test_a_turn_that_fails_midway_still_records_what_it_spent(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args, *, scope=None: StubResult({}))
    settings = make_settings(tmp_path, message_token_budget=10_000_000)

    with pytest.raises(RuntimeError, match="provider overloaded"):
        loop.run_turn(
            [], "q", session_id="s1", ip="1.2.3.4", client=FailingOnCall(3), settings=settings
        )

    assert traces.message_count_for_session("s1", settings=settings) == 1
    # Two billed calls of 1M input tokens each, at the table rate.
    assert traces.spend_today(settings=settings) == pytest.approx(
        2 * settings.agent_usd_per_mtok_in
    )


def test_a_turn_that_fails_on_its_first_call_records_nothing(tmp_path):
    settings = make_settings(tmp_path)
    with pytest.raises(RuntimeError):
        loop.run_turn(
            [], "q", session_id="s1", ip="1.2.3.4", client=FailingOnCall(1), settings=settings
        )
    assert traces.message_count_for_session("s1", settings=settings) == 0
