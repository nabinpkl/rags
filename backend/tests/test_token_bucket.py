import pytest

from askrag.ingest.token_bucket import TokenBucket


class FakeClock:
    """A clock that only moves when something sleeps on it."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def bucket(tokens_per_minute: int = 60_000) -> tuple[TokenBucket, FakeClock]:
    clock = FakeClock()
    return (
        TokenBucket(tokens_per_minute, monotonic=clock.monotonic, sleep=clock.sleep),
        clock,
    )


def test_the_first_take_goes_through_and_reserves_its_own_time():
    # 60,000/min is 1,000/s, so 2,000 tokens occupy the next two seconds.
    paced, clock = bucket()
    assert paced.take(2_000) == 0.0
    assert clock.slept == []


def test_a_second_take_waits_out_the_first_one_rather_than_bursting():
    paced, clock = bucket()
    paced.take(2_000)
    assert paced.take(1_000) == pytest.approx(2.0)
    # The wait was actually slept, not merely reported.
    assert clock.slept == [pytest.approx(2.0)]


def test_idle_time_banks_no_credit_for_a_later_burst():
    """The whole reason this is not a sliding window: an empty recent history
    must not read as free capacity (five 429s, DECISIONS.md 2026-09-18)."""
    paced, clock = bucket()
    paced.take(1_000)  # occupies one second
    clock.now += 600.0  # ten idle minutes, which a window would treat as credit
    assert paced.take(1_000) == 0.0  # one batch runs ahead of schedule, no more
    assert paced.take(1_000) == pytest.approx(1.0)


def test_the_sustained_rate_is_the_configured_rate():
    paced, clock = bucket(60_000)
    started = clock.now
    for _ in range(10):
        paced.take(3_000)
    # 30,000 tokens at 1,000/s: the first batch is free, the other nine wait.
    assert clock.now - started == pytest.approx(27.0)


def test_a_rate_of_zero_is_refused_rather_than_silently_unpaced():
    with pytest.raises(ValueError, match="must be positive"):
        TokenBucket(0)


def test_a_negative_take_is_a_caller_bug():
    paced, _ = bucket()
    with pytest.raises(ValueError, match="must not be negative"):
        paced.take(-1)
