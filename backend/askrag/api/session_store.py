"""Ephemeral, TTL'd, in-memory chat session state (#30; D11/D13/§6).

Holds the LIVE conversation history for one browser tab — the `messages`
list `loop.run_turn` threads between turns. This is NOT the durable record:
`traces.py`/`traces.db` persists every run for budgets, evals, and replay;
this store exists only so a session's next turn doesn't have to resend its
whole history from the client. Sessions are lost on process restart, which
is the correct §6 posture (ephemeral, server-side, no durable per-visitor
state beyond the audit trail) — not a bug to work around.

Single FastAPI process (D13: no Redis, no second store) — a plain dict is
the whole implementation. One `SessionStore` instance lives on `app.state`
(app.py's lifespan), shared across requests via `Depends`.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from askrag.config import Settings, get_settings


@dataclass(frozen=True)
class SessionEntry:
    """One session's live state: the running message history threaded
    between turns, and when it was last touched (the TTL clock)."""

    messages: list[Any]
    last_seen: float


class SessionStore:
    """get-or-create + save-after-turn + evict-expired-on-access.

    `clock` defaults to `time.monotonic` (immune to wall-clock changes);
    tests inject a fake to drive TTL expiry without real sleeps.
    """

    def __init__(
        self, *, settings: Settings | None = None, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._clock = clock
        self._sessions: dict[str, SessionEntry] = {}

    def _evict_expired(self) -> None:
        ttl = self._settings.session_ttl_seconds
        now = self._clock()
        expired = [sid for sid, entry in self._sessions.items() if now - entry.last_seen > ttl]
        for sid in expired:
            del self._sessions[sid]

    def get_or_create(self, session_id: str) -> list[Any]:
        """Return a copy of the session's message history — empty if the
        session is new or has expired. Evicts every expired session first,
        so an access always sees TTL-current state."""
        self._evict_expired()
        entry = self._sessions.get(session_id)
        return list(entry.messages) if entry is not None else []

    def save(self, session_id: str, messages: list[Any]) -> None:
        """Persist one turn's updated history and refresh the TTL clock."""
        self._evict_expired()
        self._sessions[session_id] = SessionEntry(messages=messages, last_seen=self._clock())

    def __len__(self) -> int:
        return len(self._sessions)
