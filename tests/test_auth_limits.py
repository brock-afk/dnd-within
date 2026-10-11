import threading

import pytest

from app.auth import limits, security
from app.auth.limits import AttemptLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_until_window_passes():
    clock = Clock()
    limiter = AttemptLimiter(limit=3, window=60, clock=clock)
    assert all(limiter.attempt("1.2.3.4") for _ in range(3))
    assert not limiter.attempt("1.2.3.4")
    clock.now = 59
    assert not limiter.attempt("1.2.3.4")
    clock.now = 60
    assert limiter.attempt("1.2.3.4")


def test_blocked_attempts_dont_extend_the_wait():
    clock = Clock()
    limiter = AttemptLimiter(limit=1, window=60, clock=clock)
    assert limiter.attempt("a")
    clock.now = 30
    assert not limiter.attempt("a")
    clock.now = 60
    assert limiter.attempt("a")


def test_keys_are_separate():
    limiter = AttemptLimiter(limit=1, window=60, clock=Clock())
    assert limiter.attempt("a")
    assert limiter.attempt("b")
    assert not limiter.attempt("a")


def test_refund_gives_back_one_attempt_only():
    limiter = AttemptLimiter(limit=3, window=60, clock=Clock())
    for _ in range(3):
        limiter.attempt("a")
    limiter.refund("a")  # a success refunds itself, not the failed guesses before it
    assert limiter.attempt("a")
    assert not limiter.attempt("a")


def test_refund_of_unknown_key_is_harmless():
    limiter = AttemptLimiter(limit=1, window=60, clock=Clock())
    limiter.refund("a")
    assert limiter.attempt("a")


def test_sweep_runs_at_most_once_a_minute():
    clock = Clock()
    limiter = AttemptLimiter(limit=1, window=30, clock=clock)
    limiter.attempt("a")
    clock.now = 59
    limiter.attempt("b")
    assert set(limiter._attempts) == {"a", "b"}  # "a" is stale, but no sweep yet
    clock.now = 60
    limiter.attempt("c")
    assert set(limiter._attempts) == {"b", "c"}


def test_oldest_key_is_dropped_past_the_cap(monkeypatch):
    monkeypatch.setattr(limits, "MAX_KEYS", 2)
    limiter = AttemptLimiter(limit=1, window=60, clock=Clock())
    for key in "abc":
        limiter.attempt(key)
    assert set(limiter._attempts) == {"b", "c"}


@pytest.mark.parametrize(
    "host, key",
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("", ""),
        ("testclient", "testclient"),
    ],
)
def test_client_key_groups_ipv6_by_64(host, key):
    assert limits.client_key(host) == key


def test_hashing_turns_away_when_slots_are_full(monkeypatch):
    monkeypatch.setattr(security, "_slots", threading.BoundedSemaphore(0))
    monkeypatch.setattr(security, "SLOT_WAIT_SECONDS", 0.01)
    with pytest.raises(security.HashingBusy):
        security.verify_password(None, "password")


def test_slot_is_released_after_verifying(monkeypatch):
    monkeypatch.setattr(security, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(security, "SLOT_WAIT_SECONDS", 0.01)
    hashed = security.hash_password("correct horse")
    assert security.verify_password(hashed, "correct horse")
    assert not security.verify_password(hashed, "wrong")
