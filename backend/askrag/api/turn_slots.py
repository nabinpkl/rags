"""How many live agent turns may run at once in this process (D11/D13).

The budget gate reads spend that is written only after a turn ends, so every
turn already running passes it; a fixed number of slots is what turns that
window into a bound (at most `chat_max_concurrent_turns` turns past the cap).
It also keeps chat off the worker-thread pool the sync routes share.

A plain counter, not a lock: every caller runs on the event loop thread, and
neither method awaits, so check-and-take cannot interleave.
"""


class TurnSlots:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._in_use = 0

    @property
    def full(self) -> bool:
        return self._in_use >= self._capacity

    def try_acquire(self) -> bool:
        if self.full:
            return False
        self._in_use += 1
        return True

    def release(self) -> None:
        if self._in_use == 0:
            raise RuntimeError("TurnSlots.release() without a matching acquire")
        self._in_use -= 1

    @property
    def in_use(self) -> int:
        return self._in_use
