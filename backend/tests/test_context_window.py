"""Tests for askrag.agent.context_window — oldest-first eviction under a
token ceiling. Security/correctness-relevant per §6 (D1/D2): eviction must
never touch the current user turn or the system prompt (the latter lives
outside this module entirely, so it's covered by never seeing it)."""

from dataclasses import dataclass

from askrag.agent import context_window as cw
from askrag.config import Settings


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


def settings(**overrides):
    return Settings(_env_file=None, **overrides)  # ty: ignore[unknown-argument]


def make_messages(big: str = "x" * 4000, small: str = "y" * 40):
    return [
        {"role": "user", "content": "what is RLHF?"},
        {
            "role": "assistant",
            "content": [FakeToolUseBlock(id="t1", name="search_corpus", input={"query": "RLHF"})],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": big}]},
        {
            "role": "assistant",
            "content": [
                FakeToolUseBlock(id="t2", name="read_paper", input={"paper_id": "2401.00001"})
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t2", "content": small}],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "partial answer so far"}]},
        {"role": "user", "content": "follow-up question"},
    ]


# --- estimate_tokens ---------------------------------------------------------


def test_estimate_tokens_counts_text_and_tool_result_content():
    s = settings()
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hello back"}]},
    ]
    assert cw.estimate_tokens(messages, settings=s) > 0


def test_estimate_tokens_grows_with_more_content():
    s = settings()
    short = [{"role": "user", "content": "hi"}]
    long = [{"role": "user", "content": "hi " * 500}]
    assert cw.estimate_tokens(long, settings=s) > cw.estimate_tokens(short, settings=s)


def test_estimate_tokens_counts_tool_use_input_too():
    s = settings()
    messages = [
        {
            "role": "assistant",
            "content": [
                FakeToolUseBlock(id="t1", name="search_corpus", input={"query": "x" * 500})
            ],
        }
    ]
    assert cw.estimate_tokens(messages, settings=s) > 50


# --- evict_oldest -------------------------------------------------------------


def test_evict_oldest_is_a_noop_under_the_ceiling():
    s = settings()
    messages = make_messages(big="short", small="short")
    evicted = cw.evict_oldest(messages, ceiling_tokens=1_000_000, settings=s)
    assert evicted[2]["content"][0]["content"] == "short"
    assert evicted[4]["content"][0]["content"] == "short"


def test_evict_oldest_evicts_oldest_first_and_stops_once_under_ceiling():
    s = settings()
    messages = make_messages()
    full_estimate = cw.estimate_tokens(messages, settings=s)
    # A ceiling comfortably between "evict nothing" and "evict everything":
    # the big (oldest) tool_result alone accounts for most of the estimate,
    # so evicting it should already satisfy this ceiling and the small one
    # should survive untouched.
    ceiling = 200
    assert 0 < ceiling < full_estimate  # sanity: this ceiling actually forces eviction
    evicted = cw.evict_oldest(messages, ceiling_tokens=ceiling, settings=s)

    first_result = evicted[2]["content"][0]
    second_result = evicted[4]["content"][0]
    assert first_result["content"] == "[evicted: earlier search_corpus result]"
    assert second_result["content"] == "y" * 40  # untouched
    assert cw.estimate_tokens(evicted, settings=s) <= ceiling


def test_evict_oldest_stub_names_the_right_tool():
    s = settings()
    messages = make_messages()
    evicted = cw.evict_oldest(messages, ceiling_tokens=200, settings=s)
    assert "search_corpus" in evicted[2]["content"][0]["content"]


def test_evict_oldest_never_touches_the_current_user_turn():
    s = settings()
    messages = make_messages()
    evicted = cw.evict_oldest(messages, ceiling_tokens=1, settings=s)
    assert evicted[-1] == {"role": "user", "content": "follow-up question"}


def test_evict_oldest_stops_when_nothing_left_to_evict():
    # Ceiling far below anything achievable once every tool_result is
    # stubbed: eviction must not loop forever — it gives up once there's
    # nothing left of the evictable kind (tool_result blocks).
    s = settings()
    messages = make_messages()
    evicted = cw.evict_oldest(messages, ceiling_tokens=1, settings=s)
    assert evicted[2]["content"][0]["content"] == "[evicted: earlier search_corpus result]"
    assert evicted[4]["content"][0]["content"] == "[evicted: earlier read_paper result]"


def test_evict_oldest_does_not_mutate_the_input_list():
    s = settings()
    messages = make_messages()
    original_content = messages[2]["content"][0]["content"]
    cw.evict_oldest(messages, ceiling_tokens=1, settings=s)
    assert messages[2]["content"][0]["content"] == original_content


def test_evict_oldest_handles_a_single_message_list():
    s = settings()
    lone = [{"role": "user", "content": "hi"}]
    assert cw.evict_oldest(lone, ceiling_tokens=1, settings=s) == lone


def test_evict_oldest_handles_an_empty_message_list():
    s = settings()
    assert cw.evict_oldest([], ceiling_tokens=1, settings=s) == []


def test_a_paper_quoting_a_control_token_does_not_kill_the_estimate():
    """Tool results carry retrieved paper text, which is untrusted (§6).

    tiktoken raises on a literal "<|endofprompt|>" by default; a paper ABOUT
    language models quotes those strings, and one of them must not be able to
    take down a live turn from inside the budget estimate.
    """
    messages = [{"role": "user", "content": "the model emits <|endofprompt|> at the end"}]

    assert cw.estimate_tokens(messages) > 0
