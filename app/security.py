from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()

# Verified against when the username doesn't exist, so a missing user takes
# about as long as a wrong password and usernames can't be probed by timing.
_DUMMY_HASH = _hasher.hash("dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except VerificationError:
        return False
    return password_hash is not None
