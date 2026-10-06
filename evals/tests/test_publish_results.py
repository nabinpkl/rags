"""The benchmarks page's export (§4c decision 2 amendment 2026-10-06). A run
is handed in as Retrieved records and titles come from a stub, so nothing
here touches corpus.db or a provider."""

import random

import pytest

from evals.export_benchmarks import LOCAL_RERANK, bootstrap_ci, build, rank_of
from evals.golden_set import Difficulty, GoldenChecks, GoldenRecord, GoldenType
from evals.run_retrieval_evals import CONFIGS
from evals.run_store import Retrieved

CHECKS = GoldenChecks(
    passage_verbatim=True,
    passage_within_cap=True,
    lexical_rule=True,
    question_within_cap=True,
    grounded=True,
    substantive=True,
    answer_correct=True,
    closed_book_correct=False,
    natural=True,
    unambiguous=True,
    check_model="checker",
)


def record(rid: str, question: str, chunks: list[str], type_: GoldenType) -> GoldenRecord:
    return GoldenRecord(
        id=rid,
        question=question,
        type=type_,
        expected_paper_id=chunks[0].split("#")[0],
        expected_chunk_ids=chunks,
        expected_passage="the error is bounded by",
        expected_answer="by a constant",
        difficulty=Difficulty.MEDIUM,
        draft_model="drafter",
        checks=CHECKS,
    )


def run(ranked: dict[str, list[str]], usd: float = 0.0) -> Retrieved:
    every = {c: ranked.get(c, ranked["hybrid"]) for c in CONFIGS}
    return Retrieved(every, every, dict.fromkeys(CONFIGS, 0.1), dict.fromkeys(CONFIGS, usd))


def meta(chunk_id: str) -> dict[str, str]:
    return {
        "id": chunk_id,
        "paper": chunk_id.split("#")[0],
        "section": "2 Method",
        "title": "A Paper",
    }


RECORDS = [
    record("a", "how does a bound the error", ["p#1"], GoldenType.SINGLE_HOP),
    record("b", "which two parts of b agree", ["q#1", "q#2"], GoldenType.MULTI_HOP),
]
DONE = {
    "a": run({"hybrid": ["x#1", "p#1"], "rerank": ["p#1", "p#3", "x#1"]}, usd=0.001),
    "b": run({"hybrid": ["q#2", "y#1"]}),
}


def export(**kw):
    return build(RECORDS, DONE, meta, k=10, pool_k=50, facts={"run_id": "abc"}, **kw)


def test_board_holds_every_config_plus_the_pinned_row_best_first():
    data = export(examples=["how does a bound the error"])
    configs = [b["config"] for b in data["board"]]
    assert sorted(configs) == sorted([*CONFIGS, LOCAL_RERANK.config])
    recalls = [b["recall"] for b in data["board"]]
    assert recalls == sorted(recalls, reverse=True)
    pinned = next(b for b in data["board"] if b["config"] == LOCAL_RERANK.config)
    assert (pinned["lo"], pinned["run_id"]) == (None, LOCAL_RERANK.run_id)
    rerank = next(b for b in data["board"] if b["config"] == "rerank")
    assert rerank["usd"] == pytest.approx(0.0005)
    assert rerank["run_id"] is None


def test_query_ranks_name_each_expected_passage_and_misses_are_none():
    data = export(examples=["how does a bound the error"])
    by_q = {q["question"]: q["rank"] for q in data["queries"]}
    assert by_q["how does a bound the error"]["hybrid"] == [2]
    assert by_q["how does a bound the error"]["rerank"] == [1]
    assert by_q["which two parts of b agree"]["hybrid"] == [None, 1]
    # single_hop sorts before multi_hop
    assert [q["type"] for q in data["queries"]] == ["single_hop", "multi_hop"]


def test_by_type_skips_empty_types_and_carries_the_pinned_value():
    data = export(examples=["how does a bound the error"])
    assert [t["type"] for t in data["by_type"]] == ["single_hop", "multi_hop"]
    assert data["by_type"][1]["recall"]["hybrid"] == 0.5
    assert data["by_type"][0]["recall"][LOCAL_RERANK.config] == LOCAL_RERANK.by_type["single_hop"]


def test_examples_grade_passages_and_carry_no_text():
    (ex,) = export(examples=["how does a bound the error"])["examples"]
    assert [x["grade"] for x in ex["rerank"]] == [2, 1, 0]
    assert ex["rank"]["hybrid"] == 2
    assert set(ex["expected"]) == {"id", "paper", "section", "title"}


def test_a_question_missing_from_the_run_raises():
    with pytest.raises(ValueError, match="lacks 1 questions"):
        build(RECORDS, {"a": DONE["a"]}, meta, k=10, pool_k=50, facts={})


def test_an_example_not_in_the_set_raises():
    with pytest.raises(ValueError, match="not in the set"):
        export(examples=["no such question"])


def test_rank_of_is_one_based_and_none_when_absent():
    assert rank_of(["a", "b"], "b") == 2
    assert rank_of(["a"], "z") is None


def test_bootstrap_interval_brackets_the_mean_and_is_seeded():
    values = [1.0] * 70 + [0.0] * 30
    lo, hi = bootstrap_ci(values, random.Random(1))
    assert lo < 0.7 < hi
    assert (lo, hi) == bootstrap_ci(values, random.Random(1))
