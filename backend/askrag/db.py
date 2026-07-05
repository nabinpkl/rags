"""SQLite connection factories (spec §4c).

corpus.db opens read-only BY CONSTRUCTION (mode=ro URI), not by convention:
an injection-compromised agent must have no write path to the corpus even if
every SQL-level guard fails (spec §6). traces.db is the backend's single
writable store (D13).
"""

import sqlite3
from pathlib import Path

from askrag import telemetry
from askrag.config import get_settings

# How long a writer waits for a concurrent writer's lock before raising
# "database is locked" (traces.db, D13). A protocol fact of the WAL setup, not
# a per-deployment tunable — kept beside the connection it configures.
_BUSY_TIMEOUT_SECONDS = 5.0


def connect_corpus(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else get_settings().corpus_db_path
    # mode=ro rather than `immutable`: fails loudly if the file is absent
    # (corpus.db is produced only by `just ingest`) instead of silently
    # creating an empty DB. A read-only factory never mkdirs. as_uri()
    # percent-encodes, so spaces/% in deploy paths can't corrupt the URI.
    # Tracer is fetched per call, not cached at import: a module-level tracer
    # captured before telemetry.init() would bind to the no-op provider.
    with telemetry.get_tracer("askrag.db").start_as_current_span(
        "askrag.db.connect", attributes={"askrag.db": "corpus", "askrag.db_mode": "ro"}
    ):
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_traces(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else get_settings().traces_db_path
    # The parent may be gitignored/absent on a fresh deploy, and
    # sqlite3.connect never creates parent directories.
    path.parent.mkdir(parents=True, exist_ok=True)
    with telemetry.get_tracer("askrag.db").start_as_current_span(
        "askrag.db.connect", attributes={"askrag.db": "traces", "askrag.db_mode": "rw"}
    ):
        conn = sqlite3.connect(path, timeout=_BUSY_TIMEOUT_SECONDS)
        conn.execute("PRAGMA journal_mode=WAL")
        # WAL lets readers and one writer coexist, but concurrent WRITERS still
        # serialize; without a busy timeout the loser raises "database is
        # locked" immediately. The timeout makes it wait for the lock instead
        # (traces.db has many concurrent agent-run writers — D13).
        conn.execute(f"PRAGMA busy_timeout={int(_BUSY_TIMEOUT_SECONDS * 1000)}")
    conn.row_factory = sqlite3.Row
    return conn
