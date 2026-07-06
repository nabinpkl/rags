"""tool: query_metadata — model-supplied read-only SQL over corpus.db (§5).

The one tool whose whole point is to run text the model wrote (§6: "designed
to accept model SQL"). Safety is by construction, never by string-matching:

- `db.connect_corpus` opens SQLite with `mode=ro` (§4c) — a write statement
  fails at the file level even if every guard below were bypassed.
- `sqlite3.Cursor.execute()` refuses more than one statement per call
  (raises `ProgrammingError`) — single-statement by construction, no `;`
  splitting or regex needed.
- `Connection.set_authorizer` runs at PREPARE time, before any row is read,
  and denies every action code except SELECT/read/function calls. This is
  parse-time enforcement: ATTACH, PRAGMA, INSERT/UPDATE/DELETE/DDL, and
  multi-db access are all authorizer denials, not a keyword blocklist.
- `Connection.set_progress_handler` aborts a query once it runs past
  `query_metadata_timeout_seconds` (SQLite polls the deadline periodically
  during execution, including during `fetchmany`).
- Rows are capped by fetching `max_rows + 1` and truncating — never by
  rewriting the model's SQL with an injected LIMIT.
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from askrag import db
from askrag.config import Settings, get_settings

# How often (in SQLite VM instructions) the progress handler polls the
# deadline — a protocol tuning knob for set_progress_handler, not a caller
# tunable (SQLite docs recommend the low hundreds-to-thousands range).
_PROGRESS_HANDLER_POLL_INSTRUCTIONS = 1000

_ALLOWED_AUTHORIZER_ACTIONS = frozenset(
    {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
)


class QueryMetadataError(Exception):
    """The model's SQL was rejected or exceeded a limit — safe to surface to
    the model as a tool-result error (never a 500, never a crash, §5)."""


class QueryMetadataArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, description="a single read-only SELECT statement")


@dataclass(frozen=True)
class QueryMetadataResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool  # more rows matched than query_metadata_max_rows allows


def _authorize(
    action: int,
    _arg1: str | None,
    _arg2: str | None,
    _db_name: str | None,
    _trigger: str | None,
) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_AUTHORIZER_ACTIONS else sqlite3.SQLITE_DENY


def run(
    args: QueryMetadataArgs,
    *,
    settings: Settings | None = None,
    corpus_db_path: Path | None = None,
) -> QueryMetadataResult:
    settings = settings if settings is not None else get_settings()
    conn = db.connect_corpus(corpus_db_path)
    try:
        conn.set_authorizer(_authorize)
        deadline = time.monotonic() + settings.query_metadata_timeout_seconds
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0,
            _PROGRESS_HANDLER_POLL_INSTRUCTIONS,
        )
        try:
            cursor = conn.execute(args.sql)
            columns = tuple(d[0] for d in cursor.description or ())
            fetched = cursor.fetchmany(settings.query_metadata_max_rows + 1)
        except sqlite3.Error as exc:
            raise QueryMetadataError(str(exc)) from exc

        truncated = len(fetched) > settings.query_metadata_max_rows
        rows = tuple(tuple(row) for row in fetched[: settings.query_metadata_max_rows])
        return QueryMetadataResult(columns=columns, rows=rows, truncated=truncated)
    finally:
        conn.close()
