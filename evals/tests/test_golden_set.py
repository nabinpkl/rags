"""The golden set's shape and its integrity against corpus.db (D14 amendment
2026-09-30). The integrity tests read the committed golden.jsonl: a set whose
ground truth no longer resolves would score retrieval against nothing."""

import pytest
from askrag import db
from askrag.config import get_settings

from evals.golden_set import (
    GOLDEN_PATH,
    Difficulty,
    GoldenChecks,
    GoldenRecord,
    GoldenType,
    dump_golden,
    load_golden,
)

PASSING = dict(
    passage_verbatim=True,
    passage_within_cap=True,
    lexical_rule=True,
    grounded=True,
    substantive=True,
    answer_correct=True,
    closed_book_correct=False,
    check_model="checker",
)


def record(**checks) -> GoldenRecord:
    return GoldenRecord(
        id="single_hop-1234.5678#3",
        question="How does the method bound its error?",
        type=GoldenType.SINGLE_HOP,
        expected_paper_id="1234.5678",
        expected_chunk_ids=["1234.5678#3"],
        expected_passage="the error is bounded by",
        expected_answer="by a constant",
        difficulty=Difficulty.MEDIUM,
        draft_model="drafter",
        checks=GoldenChecks.model_validate({**PASSING, **checks}),
    )


def test_a_record_passing_every_check_counts():
    assert record().counts()


@pytest.mark.parametrize(
    "failed",
    [
        {"passage_verbatim": False},
        {"passage_within_cap": False},
        {"lexical_rule": False},
        {"grounded": False},
        {"substantive": False},
        {"answer_correct": False},
        # answerable closed-book: it would test the model, not retrieval
        {"closed_book_correct": True},
    ],
)
def test_any_failed_check_culls(failed):
    assert not record(**failed).counts()


def test_load_keeps_culled_records_only_on_request(tmp_path):
    path = tmp_path / "golden.jsonl"
    dump_golden([record(), record(grounded=False)], path)
    assert len(load_golden(path)) == 1
    assert len(load_golden(path, counted_only=False)) == 2


def test_a_malformed_line_raises(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text('{"id": "x"}\n')
    with pytest.raises(ValueError):
        load_golden(path)


# --- the committed set ------------------------------------------------------

needs_corpus = pytest.mark.skipif(
    not get_settings().corpus_db_path.exists(), reason="corpus.db not present"
)


@pytest.fixture(scope="module")
def committed() -> list[GoldenRecord]:
    return load_golden(GOLDEN_PATH, counted_only=False)


def test_the_set_is_big_enough_to_gate_a_decision(committed):
    counted = [r for r in committed if r.counts()]
    assert len(counted) >= 50
    # every failure axis is present, or the set cannot say where a config fails
    assert {r.type for r in counted} == set(GoldenType)


def test_ids_are_unique(committed):
    assert len({r.id for r in committed}) == len(committed)


@needs_corpus
def test_every_expected_chunk_resolves_in_its_paper(committed):
    conn = db.connect_corpus(None)
    try:
        for r in committed:
            for chunk_id in r.expected_chunk_ids:
                row = conn.execute(
                    "SELECT paper_id FROM chunks WHERE chunk_id = ?", (chunk_id,)
                ).fetchone()
                assert row is not None, f"{r.id}: {chunk_id} is not in corpus.db"
                assert row["paper_id"] == r.expected_paper_id, r.id
    finally:
        conn.close()
