"""Checkpointing a redraft: records survive a kill and are reused only by a
run with the same signature."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.draft_progress import ProgressLog, load_progress, signature
from evals.golden_set import Difficulty, DraftedRecord, GoldenChecks, GoldenType

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


def record(rid: str) -> DraftedRecord:
    return DraftedRecord(
        id=rid,
        question="how do sparse models scale",
        type=GoldenType.SINGLE_HOP,
        expected_paper_id="p",
        expected_chunk_ids=["p#1"],
        expected_passage="span",
        expected_answer="answer",
        difficulty=Difficulty.EASY,
        draft_model="drafter",
        checks=CHECKS,
    )


def test_signature_moves_with_any_part():
    assert signature(["a", 1]) == signature(["a", 1])
    assert signature(["a", 1]) != signature(["a", 2])


def test_no_progress_file_resumes_nothing(tmp_path: Path):
    assert load_progress("abc", tmp_path / "none.jsonl") == {}


def test_records_reload_under_their_own_signature_only(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    ProgressLog("old", path).append(record("single_hop-p#1"))
    ProgressLog("new", path).append(record("single_hop-p#2"))
    assert list(load_progress("new", path)) == ["single_hop-p#2"]
    assert list(load_progress("old", path)) == ["single_hop-p#1"]
    assert load_progress("other", path) == {}


def test_parallel_appends_each_land_on_their_own_line(tmp_path: Path):
    path = tmp_path / "progress.jsonl"
    log = ProgressLog("sig", path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(log.append, [record(f"single_hop-p#{i}") for i in range(200)]))
    assert len(load_progress("sig", path)) == 200
