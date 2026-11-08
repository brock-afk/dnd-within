import threading
from contextlib import contextmanager

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()

_TIMING_DECOY_HASH = _hasher.hash("timing-decoy")

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
            _hasher.verify(password_hash or _TIMING_DECOY_HASH, password)
        except VerificationError:
            return False
    return password_hash is not None
