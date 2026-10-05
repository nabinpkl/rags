"""Loading rewrites (#18): a rewrite counts only for the question it rewrote."""

from pathlib import Path

import pytest

from evals.golden_set import Difficulty, GoldenChecks, GoldenRecord, GoldenType
from evals.rewrite_queries import Rewrite, load_rewrites

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


def record(rid: str, question: str) -> GoldenRecord:
    return GoldenRecord(
        id=rid,
        question=question,
        type=GoldenType.SINGLE_HOP,
        expected_paper_id="p",
        expected_chunk_ids=["p#1"],
        expected_passage="span",
        expected_answer="answer",
        difficulty=Difficulty.EASY,
        draft_model="drafter",
        checks=CHECKS,
    )


def write(path: Path, *rewrites: Rewrite) -> Path:
    path.write_text("".join(r.model_dump_json() + "\n" for r in rewrites))
    return path


def rewrite(rid: str, question: str) -> Rewrite:
    return Rewrite(id=rid, question=question, rewrite="field terms", model="m", seconds=1.0)


def test_rewrites_load_by_record_id(tmp_path: Path):
    path = write(tmp_path / "r.jsonl", rewrite("q1", "how do sparse models scale"))
    got = load_rewrites([record("q1", "how do sparse models scale")], path)
    assert got["q1"].rewrite == "field terms"


@pytest.mark.parametrize(
    "stored",
    [
        rewrite("q1", "an older wording of the question"),
        rewrite("q9", "how do sparse models scale"),
    ],
)
def test_a_missing_or_stale_rewrite_raises(tmp_path: Path, stored: Rewrite):
    path = write(tmp_path / "r.jsonl", stored)
    with pytest.raises(ValueError, match="just rewrites"):
        load_rewrites([record("q1", "how do sparse models scale")], path)
