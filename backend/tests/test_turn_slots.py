"""Tests for askrag.api.turn_slots: the process-wide live-turn limit."""

import pytest

from askrag.api.turn_slots import TurnSlots


def test_acquires_up_to_capacity_then_refuses():
    slots = TurnSlots(2)
    assert slots.try_acquire() and slots.try_acquire()
    assert slots.full
    assert not slots.try_acquire()
    assert slots.in_use == 2


def test_release_frees_a_slot():
    slots = TurnSlots(1)
    assert slots.try_acquire()
    slots.release()
    assert not slots.full
    assert slots.try_acquire()


def test_release_without_acquire_raises():
    with pytest.raises(RuntimeError):
        TurnSlots(1).release()
