"""The drafter's checks, with a stubbed model: no test calls a real API."""

import json

import pytest
from askrag.config import get_settings

from evals.draft_golden_set import (
    FENCE,
    check_record,
    draft_prompt,
    lexical_rule,
    normalize,
    parse_json,
    spans_verbatim,
)
from evals.golden_set import GoldenType
from evals.sample_sources import Source, SourceChunk

TEXT = "We fine-tune with **LoRA** adapters. The rank r = 8 gives the best recall."
CHUNK = SourceChunk("1234.5678#2", "1234.5678", "cs.CL", "Method", TEXT)


def source(type_=GoldenType.SINGLE_HOP, rare=frozenset({"lora"}), anchor=None) -> Source:
    return Source(type_, (CHUNK,), rare, anchor)


class StubClient:
    """Replies in call order: closed-book answer, then the grade."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def complete_nonempty(self, model, system, user, max_tokens):
        self.prompts.append(user)
        self.systems.append(system)
        return self.replies.pop(0)


def test_parse_json_finds_the_object_inside_prose():
    assert parse_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json("no object here")


def test_normalize_drops_markdown_the_model_would_not_copy():
    assert normalize("**LoRA**  _adapters_") == "lora adapters"


def test_a_span_must_be_verbatim():
    assert spans_verbatim(["The rank r = 8 gives the best recall."], source())
    assert not spans_verbatim(["The rank r = 16 gives the best recall."], source())


def test_an_elided_span_is_checked_piece_by_piece():
    assert spans_verbatim(["We fine-tune with LoRA … gives the best recall"], source())
    assert not spans_verbatim(["We fine-tune with LoRA … gives the worst recall"], source())


def test_multi_hop_needs_a_span_from_each_chunk():
    other = SourceChunk("1234.5678#9", "1234.5678", "cs.CL", "Results", "Recall rises to 0.9.")
    pair = Source(GoldenType.MULTI_HOP, (CHUNK, other), frozenset())
    assert spans_verbatim(["rank r = 8", "Recall rises to 0.9"], pair)
    assert not spans_verbatim(["rank r = 8"], pair)


def test_lexical_rule_per_type():
    assert not lexical_rule("What rank works best for LoRA?", source())
    assert lexical_rule("What adapter rank works best?", source())
    exact = source(GoldenType.EXACT_MATCH, anchor="LoRA")
    assert lexical_rule("What rank works best for LoRA?", exact)
    assert not lexical_rule("What adapter rank works best?", exact)


def test_the_prompt_fences_paper_text_and_bans_rare_terms():
    prompt = draft_prompt(source())
    assert f"<{FENCE}>\n{TEXT}\n</{FENCE}>" in prompt
    assert "Banned terms: lora" in prompt


def test_check_record_carries_every_verdict():
    grade = {
        "grounded": True,
        "substantive": True,
        "answer_correct": True,
        "closed_book_correct": False,
        "natural": True,
        "note": "",
    }
    client = StubClient("I don't know.", json.dumps(grade))
    draft = {
        "question": "What adapter rank gave the best recall?",
        "answer": "8",
        "spans": ["The rank r = 8 gives the best recall."],
        "difficulty": "easy",
    }
    rec = check_record(source(), draft, client, get_settings())
    assert rec.counts()
    assert rec.expected_chunk_ids == ["1234.5678#2"]
    # the grader saw the closed-book answer it has to judge
    assert "Closed-book answer: I don't know." in client.prompts[1]


GRADE = {
    "grounded": True,
    "substantive": True,
    "answer_correct": True,
    "closed_book_correct": False,
    "natural": True,
    "note": "",
}
DRAFT = {
    "question": "which setting makes small fine-tuned add-ons work best",
    "answer": "rank 8",
    "spans": ["The rank r = 8 gives the best recall."],
    "difficulty": "medium",
}


@pytest.mark.parametrize("type_", [GoldenType.SINGLE_HOP, GoldenType.VOCABULARY_MISMATCH])
@pytest.mark.parametrize("natural", [True, False])
def test_every_type_counts_only_when_the_checker_finds_it_natural(type_, natural):
    client = StubClient("I don't know.", json.dumps({**GRADE, "natural": natural}))
    rec = check_record(source(type_), DRAFT, client, get_settings())
    assert '"natural"' in client.systems[1]
    assert rec.checks.natural is natural
    assert rec.counts() is natural


def test_a_question_longer_than_a_search_query_is_culled():
    cap = get_settings().golden_question_max_words
    long_draft = {**DRAFT, "question": " ".join(["setting"] * (cap + 1))}
    rec = check_record(
        source(), long_draft, StubClient("I don't know.", json.dumps(GRADE)), get_settings()
    )
    assert not rec.checks.question_within_cap
    assert not rec.counts()
