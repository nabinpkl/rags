"""A run's per-question file: appended as scored, reloaded on resume."""

from pathlib import Path

import pytest

from evals.run_store import Retrieved, append_run, load_run, run_path


def got(n: int) -> Retrieved:
    return Retrieved(
        {"hybrid": [f"p#{n}"]}, {"hybrid": [f"p#{n}", "q#1"]}, {"hybrid": 0.5}, {"hybrid": 4e-08}
    )


def test_a_missing_file_has_nothing_scored(tmp_path: Path):
    assert load_run(tmp_path / "none.jsonl") == {}


def test_appended_questions_reload_by_id(tmp_path: Path):
    path = tmp_path / "runs" / "abc.jsonl"
    append_run(path, "q1", got(1))
    append_run(path, "q2", got(2))
    assert load_run(path) == {"q1": got(1), "q2": got(2)}


def test_a_malformed_line_raises(tmp_path: Path):
    path = tmp_path / "abc.jsonl"
    path.write_text("{not json\n")
    with pytest.raises(ValueError):
        load_run(path)


def test_each_run_has_its_own_file():
    assert run_path("abc") != run_path("abd")
    assert run_path("abc").name == "abc.jsonl"
