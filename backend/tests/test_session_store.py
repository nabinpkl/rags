"""Tests for askrag.api.session_store — ephemeral, TTL'd, in-memory chat
session state (#30). TTL is driven by an injected clock, never a real
sleep."""

from askrag.api.session_store import SessionStore
from askrag.config import Settings


def make_settings(**overrides):
    return Settings(_env_file=None, **overrides)  # ty: ignore[unknown-argument]


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- get-or-create ------------------------------------------------------


def test_get_or_create_returns_empty_for_unknown_session():
    store = SessionStore(settings=make_settings())
    assert store.get_or_create("s1") == []


def test_save_then_get_or_create_returns_saved_messages():
    store = SessionStore(settings=make_settings())
    store.save("s1", [{"role": "user", "content": "hi"}])
    assert store.get_or_create("s1") == [{"role": "user", "content": "hi"}]


def test_get_or_create_returns_a_copy_not_the_live_list():
    store = SessionStore(settings=make_settings())
    store.save("s1", [{"role": "user", "content": "hi"}])
    got = store.get_or_create("s1")
    got.append({"role": "user", "content": "mutated"})
    assert store.get_or_create("s1") == [{"role": "user", "content": "hi"}]


def test_sessions_are_isolated_by_id():
    store = SessionStore(settings=make_settings())
    store.save("a", [{"role": "user", "content": "a-only"}])
    store.save("b", [{"role": "user", "content": "b-only"}])
    assert store.get_or_create("a") == [{"role": "user", "content": "a-only"}]
    assert store.get_or_create("b") == [{"role": "user", "content": "b-only"}]


# --- TTL eviction (injected clock, no real sleeps) -----------------------


def test_session_expires_after_ttl():
    clock = FakeClock()
    store = SessionStore(settings=make_settings(session_ttl_seconds=60), clock=clock)
    store.save("s1", [{"role": "user", "content": "hi"}])
    clock.advance(61)
    assert store.get_or_create("s1") == []


def test_session_survives_within_ttl():
    clock = FakeClock()
    store = SessionStore(settings=make_settings(session_ttl_seconds=60), clock=clock)
    store.save("s1", [{"role": "user", "content": "hi"}])
    clock.advance(59)
    assert store.get_or_create("s1") == [{"role": "user", "content": "hi"}]


def test_expired_sessions_are_evicted_from_the_store_on_access():
    clock = FakeClock()
    store = SessionStore(settings=make_settings(session_ttl_seconds=10), clock=clock)
    store.save("a", [])
    store.save("b", [])
    clock.advance(11)
    store.get_or_create("anything")  # any access triggers eviction sweep
    assert len(store) == 0


def test_saving_refreshes_the_ttl_clock():
    clock = FakeClock()
    store = SessionStore(settings=make_settings(session_ttl_seconds=10), clock=clock)
    store.save("s1", [])
    clock.advance(9)
    store.save("s1", [{"role": "user", "content": "still here"}])  # refreshes last_seen
    clock.advance(9)  # 18s since first save, but only 9s since the refresh
    assert store.get_or_create("s1") == [{"role": "user", "content": "still here"}]


def test_history_does_not_cross_a_scope_change():
    """Prior turns carry TOOL RESULTS — text from the papers they retrieved.

    Reusing them across a scope change would answer a question asked about one
    landing-page claim using another claim's papers: the tool scope would hold
    while the context leaked around it.
    """
    store = SessionStore(settings=Settings(_env_file=None))  # ty: ignore[unknown-argument]
    store.save("s1", [{"role": "user", "content": "about PPO"}], "1707.06347")

    assert store.get_or_create("s1", "1707.06347") != []
    assert store.get_or_create("s1", "2402.03300") == []
    assert store.get_or_create("s1", None) == []


def test_multi_turn_within_one_scope_keeps_its_history():
    """The case that matters: a follow-up question about the same claim."""
    store = SessionStore(settings=Settings(_env_file=None))  # ty: ignore[unknown-argument]
    store.save("s1", [{"role": "user", "content": "first"}], "1707.06347")

    history = store.get_or_create("s1", "1707.06347")
    store.save("s1", [*history, {"role": "user", "content": "second"}], "1707.06347")

    assert len(store.get_or_create("s1", "1707.06347")) == 2


def test_unscoped_sessions_behave_exactly_as_before():
    store = SessionStore(settings=Settings(_env_file=None))  # ty: ignore[unknown-argument]
    store.save("s1", [{"role": "user", "content": "hi"}])

    assert len(store.get_or_create("s1")) == 1
