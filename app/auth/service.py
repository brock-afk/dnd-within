from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.form import LoginForm, RegisterForm
from app.auth.limits import Throttle
from app.auth.models import User
from app.auth.queries import user_named
from app.auth.security import HashingBusy, hash_password, verify_password
from app.core.db import release_connection
from app.invites.queries import active_invite
from app.invites.service import claim


class Refusal(Enum):
    TOO_MANY = "Too many attempts. Try again in a few minutes."
    BAD_LOGIN = "Invalid username or password."
    BAD_INVITE = "That invite isn't valid. It may have expired or already been used."
    TAKEN = "That username is taken."


@contextmanager
def _refund_if_busy(throttle: Throttle) -> Iterator[None]:
    try:
        yield
    except HashingBusy:
        throttle.refund()
        raise


def log_in(db: Session, form: LoginForm, throttle: Throttle) -> User | Refusal | str:
    if problem := form.problem():
        return problem
    if not throttle.attempt():
        return Refusal.TOO_MANY
    user = user_named(db, form.username)
    release_connection(db)
    with _refund_if_busy(throttle):
        valid = verify_password(user.password_hash if user else None, form.password)
    if not valid:
        return Refusal.BAD_LOGIN
    throttle.refund()
    return user


def register(db: Session, form: RegisterForm, throttle: Throttle) -> User | Refusal | str:
    if problem := form.problem():
        return problem
    if not throttle.attempt():
        return Refusal.TOO_MANY
    if active_invite(db, form.invite_code) is None:
        return Refusal.BAD_INVITE
    taken = user_named(db, form.username) is not None
    release_connection(db)
    if taken:
        return Refusal.TAKEN
    with _refund_if_busy(throttle):
        password_hash = hash_password(form.password)
    user = _create_invited_user(db, form, password_hash)
    if isinstance(user, User):
        throttle.refund()
    return user


def _create_invited_user(db: Session, form: RegisterForm, password_hash: str) -> User | Refusal:
    savepoint = db.begin_nested()
    user = create_user(db, form.username, password_hash)
    if user is None:
        savepoint.rollback()
        return Refusal.TAKEN
    if not claim(db, form.invite_code, user):
        savepoint.rollback()
        return Refusal.BAD_INVITE
    savepoint.commit()
    return user


def create_user(db: Session, username: str, password_hash: str) -> User | None:
    user = User(username=username, password_hash=password_hash)
    try:
        with db.begin_nested():
            db.add(user)
    except IntegrityError:
        return None
    return user


def create_admin(db: Session, form: RegisterForm) -> User | Refusal | str:
    if problem := form.problem():
        return problem
    user = create_user(db, form.username, hash_password(form.password))
    if user is None:
        return Refusal.TAKEN
    user.is_admin = True
    db.flush()
    return user


def grant_admin(db: Session, username: str) -> bool:
    user = user_named(db, username)
    if user is None:
        return False
    user.is_admin = True
    db.flush()
    return True
