"""Checkpointing for `just golden`: a killed redraft resumes, it does not restart.

Each record is appended to a progress file the moment it is checked, tagged
with a signature of everything that shaped it (models, prompts, caps). A rerun
reuses the records whose signature matches and drafts only the rest; records
from a run with a different prompt or model are ignored, never mixed into the
set. The drafter deletes the file once `golden.jsonl` is written with no
failed drafts; while any failed, it stays, so a rerun retries only those.
"""

import hashlib
import json
import threading
from collections.abc import Sequence
from pathlib import Path

from evals.golden_set import GOLDEN_PATH, DraftedRecord

PROGRESS_PATH = GOLDEN_PATH.with_name("golden.progress.jsonl")


def signature(parts: Sequence[object]) -> str:
    """Twelve hex characters over the inputs that shape a record."""
    blob = json.dumps([str(p) for p in parts]).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def load_progress(sig: str, path: Path = PROGRESS_PATH) -> dict[str, DraftedRecord]:
    """Records from earlier runs with this signature, keyed by record id."""
    if not path.exists():
        return {}
    done: dict[str, DraftedRecord] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["signature"] == sig:
            record = DraftedRecord.model_validate(entry["record"])
            done[record.id] = record
    return done


class ProgressLog:
    """Appends one checked record per line; safe across drafting threads."""

    def __init__(self, sig: str, path: Path = PROGRESS_PATH) -> None:
        self.sig = sig
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: DraftedRecord) -> None:
        line = json.dumps({"signature": self.sig, "record": record.model_dump(mode="json")})
        with self._lock, self.path.open("a") as f:
            f.write(line + "\n")
