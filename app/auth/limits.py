import ipaddress
import threading
import time
from collections import deque
from collections.abc import Callable

SWEEP_SECONDS = 60
MAX_KEYS = 50_000


def client_key(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class AttemptLimiter:
    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._attempts: dict[str, deque[float]] = {}
        self._last_sweep = clock()
        self._lock = threading.Lock()

    def attempt(self, key: str) -> bool:
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
