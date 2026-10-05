"""The retrieval eval's metrics, table and README splice (#18). Rankings are
handed in, so nothing here touches the index or the embedding API."""

import math
from pathlib import Path

import pytest
from askrag.config import Settings

from evals.golden_set import Difficulty, GoldenChecks, GoldenRecord, GoldenType
from evals.run_retrieval_evals import (
    CONFIGS,
    _usd,
    fingerprint,
    ndcg_at,
    paper_recall_at,
    recall_at,
    reciprocal_rank,
    render,
    score,
    splice_readme,
)

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


def record(rid: str, chunks: list[str], type_: GoldenType = GoldenType.SINGLE_HOP):
    return GoldenRecord(
        id=rid,
        question="How does the method bound its error?",
        type=type_,
        expected_paper_id=chunks[0].split("#")[0],
        expected_chunk_ids=chunks,
        expected_passage="the error is bounded by",
        expected_answer="by a constant",
        difficulty=Difficulty.MEDIUM,
        draft_model="drafter",
        checks=CHECKS,
    )


def test_recall_counts_expected_chunks_inside_the_cutoff():
    ranked = ["a#1", "b#1", "c#1", "d#1"]
    assert recall_at(ranked, ["c#1"], 3) == 1.0
    assert recall_at(ranked, ["d#1"], 3) == 0.0


def test_recall_gives_partial_credit_for_one_of_two_hops():
    assert recall_at(["p#1", "x#1"], ["p#1", "p#9"], 5) == 0.5


def test_reciprocal_rank_uses_the_first_expected_hit_inside_k():
    assert reciprocal_rank(["x#1", "p#2", "p#1"], ["p#1", "p#2"], 10) == 0.5
    assert reciprocal_rank(["x#1"], ["p#1"], 10) == 0.0
    assert reciprocal_rank(["x#1", "p#1"], ["p#1"], 1) == 0.0


def test_ndcg_is_one_at_the_top_and_discounts_lower_ranks():
    assert ndcg_at(["p#1", "x#1"], ["p#1"], 10) == 1.0
    assert ndcg_at(["x#1", "p#1"], ["p#1"], 10) == pytest.approx(1 / math.log2(3))
    assert ndcg_at(["x#1", "p#1"], ["p#1"], 1) == 0.0
    # two expected chunks, one found first: DCG 1 against an ideal of 1 + 1/log2(3)
    assert ndcg_at(["p#1", "x#1"], ["p#1", "p#2"], 10) == pytest.approx(1 / (1 + 1 / math.log2(3)))


def test_paper_recall_accepts_any_chunk_of_the_paper():
    assert paper_recall_at(["x#1", "p#7"], "p", 2) == 1.0
    assert paper_recall_at(["x#1", "p#7"], "p", 1) == 0.0


def test_score_averages_over_records():
    records = [record("q1", ["p#1"]), record("q2", ["r#1"])]
    rankings = {"q1": {"bm25": ["p#1"]}, "q2": {"bm25": ["x#1", "r#1"]}}
    assert score(records, rankings, "bm25", 1).recall == 0.5
    s = score(records, rankings, "bm25", 5)
    assert s.n == 2
    assert s.recall == 1.0
    assert s.mrr == pytest.approx(0.75)


def test_score_refuses_an_empty_set():
    with pytest.raises(ValueError):
        score([], {}, "bm25", 5)


LATENCY = {c: 12.0 for c in CONFIGS}
COST = {c: 0.0 if c == "bm25" else 0.00068 for c in CONFIGS}


def test_render_ranks_configs_best_first_and_has_a_row_per_present_type():
    records = [
        record("q1", ["p#1"]),
        record("q2", ["r#1", "r#4"], GoldenType.MULTI_HOP),
    ]
    rankings = {r.id: {c: list(r.expected_chunk_ids) for c in CONFIGS} for r in records}
    rankings["q1"]["bm25"] = ["x#1"]
    pools = {r.id: {c: ["x#1", *r.expected_chunk_ids] for c in CONFIGS} for r in records}
    pools["q2"]["hybrid"] = ["r#1"]
    table = render(
        records, rankings, pools, LATENCY, COST, 10, 50, n_papers=2, n_chunks=10, run_id="abc"
    )
    assert "| Hybrid (RRF) | 100% | 1.00 | 1.00 | 100% | 75% | 12 ms | $0.00068 |" in table
    assert "| Keyword (BM25) | 50% | 0.50 | 0.50 | 50% | 100% | 12 ms | $0 |" in table
    assert "| Rewrite + hybrid | 100% |" in table
    assert "| Hybrid + rerank | 100% |" in table
    assert table.index("Hybrid (RRF) |") < table.index("Keyword (BM25) |")
    assert "| multi_hop | 1 |" in table
    assert "known_hard" not in table
    assert "common field words" not in table
    assert "model-checked" in table
    assert "top 10 the agent reads" in table


README = "intro\n<!-- retrieval-evals:start -->\nold\n<!-- retrieval-evals:end -->\noutro\n"


def test_splice_replaces_only_the_marked_block():
    out = splice_readme(README, "new table\n")
    assert out == (
        "intro\n<!-- retrieval-evals:start -->\nnew table\n<!-- retrieval-evals:end -->\noutro\n"
    )
    assert splice_readme(out, "new table\n") == out


def test_splice_fails_without_markers():
    with pytest.raises(ValueError):
        splice_readme("no markers here", "t\n")


def test_fingerprint_moves_with_the_set_its_rewrites_and_the_constants(tmp_path: Path):
    golden, rewrites = tmp_path / "golden.jsonl", tmp_path / "rewrites.jsonl"
    golden.write_text("a\n")
    rewrites.write_text("a\n")

    def fp(settings: Settings, n_chunks: int = 100) -> str:
        return fingerprint(settings, golden, n_chunks, rewrites)

    base = fp(Settings())
    assert fp(Settings()) == base
    assert fp(Settings(rrf_k=10)) != base
    assert fp(Settings(search_top_k=5)) != base
    assert fp(Settings(eval_pool_k=20)) != base
    assert fp(Settings(rerank_openrouter_model="cohere/rerank-4-fast")) != base
    assert fp(Settings(rerank_backend="local")) != base
    assert fp(Settings(), 101) != base
    rewrites.write_text("b\n")
    assert fp(Settings()) != base
    rewrites.write_text("a\n")
    golden.write_text("b\n")
    assert fp(Settings()) != base


def test_render_explains_the_mismatch_row():
    records = [record("q1", ["p#1"], GoldenType.VOCABULARY_MISMATCH)]
    rankings = {"q1": {c: ["p#1"] for c in CONFIGS}}
    table = render(
        records, rankings, rankings, LATENCY, COST, 5, 50, n_papers=1, n_chunks=1, run_id="abc"
    )
    assert "only on common field words" in table


@pytest.mark.parametrize(
    ("usd", "shown"),
    [(0.0, "$0"), (4.14e-08, "<$0.000001"), (0.000659, "$0.000659"), (4.32e-05, "$0.000043")],
)
def test_costs_print_as_plain_dollars(usd, shown):
    assert _usd(usd) == shown
