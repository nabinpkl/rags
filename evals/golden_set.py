"""The golden set's record shape and loader (D14, amended 2026-09-30).

The one home for the schema: the drafter writes these records, and the
retrieval and answer evals read them. `golden.jsonl` is dataset-as-code, one
record per line, so a change to the set shows up as a line diff in review.

The set exists twice. The drafted copy, under `corpus/` and never committed,
keeps each record's verbatim passage: the drafter's checks read it and it
re-anchors the chunk ids when chunking changes. The committed copy drops the
passage, because a public repo publishing every quote at once would carry
more of a paper than any answer may (§6c); scoring needs only the chunk ids.

A record counts on its checks alone (no human pass, D14 amendment
2026-09-30): `counts()` is the single definition of "in the set", so no
consumer re-derives it and gets it subtly different.
"""

import json
from enum import StrEnum
from pathlib import Path

from askrag.config import Settings
from pydantic import BaseModel, ConfigDict, Field

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"


class GoldenType(StrEnum):
    """The failure axes the set stresses (D14 amendment 2026-07-09)."""

    SINGLE_HOP = "single_hop"  # a researcher's question in their own words
    EXACT_MATCH = "exact_match"  # hinges on a distinctive term: the BM25 leg
    MULTI_HOP = "multi_hop"  # needs two chunks of one paper together
    KNOWN_HARD = "known_hard"  # tables and math, D6's honest floor
    # the searcher's own words for a need the paper names in its own terms:
    # where keyword matching structurally fails and the vector leg must carry
    VOCABULARY_MISMATCH = "vocabulary_mismatch"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GoldenChecks(BaseModel):
    """What stands in for the human pass. Every field is recorded, pass or
    fail, so a culled candidate says why it was culled."""

    model_config = ConfigDict(extra="forbid")

    passage_verbatim: bool  # expected_passage sits inside its chunk
    passage_within_cap: bool  # at most quote_max_words (§6c)
    lexical_rule: bool  # exact_match names its anchor; others avoid rare terms
    question_within_cap: bool  # at most golden_question_max_words
    grounded: bool  # checker: the passage alone answers the question
    substantive: bool  # checker: technical content, not venue/author trivia
    answer_correct: bool  # checker: the drafted answer is right by the passage
    closed_book_correct: bool  # checker answered it WITHOUT the passage
    # checker: a researcher would really type this into a paper search, not a
    # prompt written from the paper or a contrived rewording of a known term
    natural: bool
    # checker: the expected answer is not wrong for the query as typed, as it
    # is when it holds only for a special case the query leaves unnamed
    unambiguous: bool
    check_model: str
    note: str = ""


class GoldenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str = Field(min_length=10)
    type: GoldenType
    expected_paper_id: str
    expected_chunk_ids: list[str] = Field(min_length=1)
    expected_answer: str
    difficulty: Difficulty
    # The term an exact_match question hinges on; None for the other types.
    anchor_term: str | None = None
    draft_model: str
    checks: GoldenChecks

    def counts(self) -> bool:
        """In the set: every deterministic check and every checker verdict
        passed, and the question needs retrieval to answer."""
        c = self.checks
        return (
            c.passage_verbatim
            and c.passage_within_cap
            and c.lexical_rule
            and c.question_within_cap
            and c.grounded
            and c.substantive
            and c.answer_correct
            and not c.closed_book_correct
            and c.natural
            and c.unambiguous
        )


class DraftedRecord(GoldenRecord):
    """A record as drafted, with the passage the committed copy drops."""

    # Verbatim span(s) of the expected chunk(s), joined with " … " for
    # multi_hop. The ids move when chunking constants do (#19); this is what
    # re-anchors them.
    expected_passage: str


def drafted_path(settings: Settings) -> Path:
    return settings.corpus_dir / "evals" / "golden.jsonl"


def load_golden(path: Path = GOLDEN_PATH, *, counted_only: bool = True) -> list[GoldenRecord]:
    """Parse every line; a malformed line raises rather than being skipped."""
    records = [
        GoldenRecord.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    return [r for r in records if r.counts()] if counted_only else records


def load_drafted(path: Path) -> list[DraftedRecord]:
    return [
        DraftedRecord.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def dump_golden(records: list[DraftedRecord], drafted: Path, public: Path = GOLDEN_PATH) -> None:
    """Both copies from one list, so the committed set never drifts from the
    drafted one it was cut from."""
    drafted.parent.mkdir(parents=True, exist_ok=True)
    drafted.write_text("".join(r.model_dump_json() + "\n" for r in records))
    public.write_text(
        "".join(r.model_dump_json(exclude={"expected_passage"}) + "\n" for r in records)
    )
