import secrets
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.form import LoginForm, RegisterForm
from app.auth.limits import Throttle
from app.auth.models import User
from app.auth.queries import invite_required, user_named
from app.auth.security import HashingBusy, hash_password, verify_password
from app.core.config import settings
from app.core.db import release_connection

TOO_MANY = "Too many attempts. Try again in a few minutes."
BAD_LOGIN = "Invalid username or password."
BAD_INVITE = "That invite code isn't right."
TAKEN = "That username is taken."


@contextmanager
def _refund_if_busy(throttle: Throttle) -> Iterator[None]:
    try:
        yield
    except HashingBusy:
        throttle.refund()
        raise


def log_in(db: Session, form: LoginForm, throttle: Throttle) -> tuple[User | None, str | None]:
    if not throttle.attempt():
        return None, TOO_MANY
    user = user_named(db, form.username)
    release_connection(db)
    with _refund_if_busy(throttle):
        valid = verify_password(user.password_hash if user else None, form.password)
    if not valid:
        return None, BAD_LOGIN
    throttle.refund()
    return user, None


def _invite_ok(code: str) -> bool:
    return not invite_required() or secrets.compare_digest(
        code.encode(), settings.invite_code.encode()
    )


def register(db: Session, form: RegisterForm, throttle: Throttle) -> tuple[User | None, str | None]:
    if problem := form.problem():
        return None, problem
    if not throttle.attempt():
        return None, TOO_MANY
    if not _invite_ok(form.invite_code):
        return None, BAD_INVITE
    taken = user_named(db, form.username) is not None
    release_connection(db)
    if taken:
        return None, TAKEN
    with _refund_if_busy(throttle):
        password_hash = hash_password(form.password)
    user = create_user(db, form.username, password_hash)
    if user is None:
        return None, TAKEN
    throttle.refund()
    return user, None


def create_user(db: Session, username: str, password_hash: str) -> User | None:
    user = User(username=username, password_hash=password_hash)
    try:
        with db.begin_nested():
            db.add(user)
    except IntegrityError:
        return None
    return user
