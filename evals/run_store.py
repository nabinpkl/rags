"""Per-question results of a retrieval eval run (#18), one file per run.

A run's file is `runs/<fingerprint>.jsonl`, one question per line, appended
the moment that question is scored. Rerunning with the same fingerprint
skips the questions already in the file, so a killed run resumes and a
finished one re-renders without retrieving or reranking anything (a full
run with the local reranker takes hours on the build host). A different
fingerprint is a different file: results from another set, index or
configuration never mix.

The files are committed beside the README table they produced, so the
benchmarks page and later analyses read rankings instead of recomputing.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "runs"


@dataclass(frozen=True)
class Retrieved:
    """One question's rankings at k and at the pool depth, and the seconds
    and billed dollars each config took."""

    rankings: dict[str, list[str]]
    pools: dict[str, list[str]]
    seconds: dict[str, float]
    usd: dict[str, float]


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.jsonl"


def load_run(path: Path) -> dict[str, Retrieved]:
    """Scored questions by record id; a malformed line raises."""
    if not path.exists():
        return {}
    done: dict[str, Retrieved] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            done[entry["id"]] = Retrieved(
                entry["rankings"], entry["pools"], entry["seconds"], entry["usd"]
            )
    return done


def append_run(path: Path, record_id: str, got: Retrieved) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"id": record_id, **asdict(got)}) + "\n")
