import threading
from contextlib import contextmanager

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()

# Verified against when the username doesn't exist, so a missing user takes
# about as long as a wrong password and usernames can't be probed by timing.
_DUMMY_HASH = _hasher.hash("dummy-password")

# Each hash uses 64 MiB, so only a couple run at once: a flood of logins is turned away
# instead of running the server out of memory. A hash takes ~60 ms, so a short wait covers
# real logins that collide without parking request threads for long.
_slots = threading.BoundedSemaphore(2)
SLOT_WAIT_SECONDS = 1


class HashingBusy(Exception):
    pass


@contextmanager
def _slot():
    if not _slots.acquire(timeout=SLOT_WAIT_SECONDS):
        raise HashingBusy
    try:
        yield
    finally:
        _slots.release()


def hash_password(password: str) -> str:
    with _slot():
        return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    with _slot():
        try:
            _hasher.verify(password_hash or _DUMMY_HASH, password)
        except VerificationError:
            return False
    return password_hash is not None
