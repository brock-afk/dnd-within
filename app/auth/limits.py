"""Slowing down password and invite code guessing. In-process, which is enough because the
app runs as a single process (like app/sharing/live.py)."""

import ipaddress
import threading
import time
from collections import deque
from collections.abc import Callable

SWEEP_SECONDS = 60  # how often keys with no recent attempts are forgotten
MAX_KEYS = 50_000  # past this, the oldest key is dropped, so memory stays bounded


def client_key(host: str) -> str:
    """The limiter key for a client address: IPv6 by its /64, since one user typically holds
    a whole /64 and could otherwise rotate addresses within it."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6 and address.ipv4_mapped:  # ::ffff:1.2.3.4 is just 1.2.3.4
        address = address.ipv4_mapped
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class AttemptLimiter:
    """At most `limit` attempts per key in any `window` seconds. Attempts count when they
    start, so simultaneous requests can't all slip through; one that turns out not to be a
    failed guess is given back with `refund`. A success refunds only itself: clearing the key
    would let anyone with an account wipe their failed guesses by logging into it."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._attempts: dict[str, deque[float]] = {}
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def attempt(self, key: str) -> bool:
        """Record an attempt, or return False (recording nothing) when the key is at its limit."""
        now = self.clock()
        with self._lock:
            if now - self._last_sweep >= SWEEP_SECONDS:
                self._sweep(now)
            times = self._attempts.get(key)
            if times is None:
                if len(self._attempts) >= MAX_KEYS:
                    del self._attempts[next(iter(self._attempts))]
                times = self._attempts[key] = deque()
            while times and times[0] <= now - self.window:
                times.popleft()
            if len(times) >= self.limit:
                return False
            times.append(now)
            return True

    def refund(self, key: str) -> None:
        """Give back one attempt."""
        with self._lock:
            if times := self._attempts.get(key):
                times.pop()

    def _sweep(self, now: float) -> None:
        self._last_sweep = now
        self._attempts = {
            key: times
            for key, times in self._attempts.items()
            if times and times[-1] > now - self.window
        }


auth_attempts = AttemptLimiter(limit=10, window=15 * 60)
