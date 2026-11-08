from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.limits import AttemptLimiter, Throttle, auth_attempts, client_key
from app.auth.models import User
from app.auth.security import HashingBusy
from app.core.db import DbSession
from app.core.templates import form_error, hx_redirect


class LoginRequired(Exception):
    pass


SESSION_USER = "user_id"


def start_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session[SESSION_USER] = user.id


def end_session(request: Request) -> None:
    request.session.clear()


def get_optional_user(request: Request, db: DbSession) -> User | None:
    user_id = request.session.get(SESSION_USER)
    return db.get(User, user_id) if user_id else None


def require_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise LoginRequired
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(require_user)]


def get_limiter() -> AttemptLimiter:
    return auth_attempts


def get_throttle(
    request: Request, limiter: Annotated[AttemptLimiter, Depends(get_limiter)]
) -> Throttle:
    return Throttle(limiter, client_key(request.client.host if request.client else ""))


ClientThrottle = Annotated[Throttle, Depends(get_throttle)]


def login_required_handler(request: Request, exc: LoginRequired) -> Response:
    if request.headers.get("HX-Request"):
        return hx_redirect("/login")
    return RedirectResponse("/login", status_code=303)


def hashing_busy_handler(request: Request, exc: HashingBusy) -> Response:
    return form_error(request, "The server is busy. Try again in a moment.", status_code=503)
