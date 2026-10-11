from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.models import User
from app.auth.security import HashingBusy
from app.core.db import DbSession
from app.core.templates import form_error, hx_redirect


class LoginRequired(Exception):
    pass


def get_optional_user(request: Request, db: DbSession) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def require_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise LoginRequired
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(require_user)]


def login_required_handler(request: Request, exc: LoginRequired) -> Response:
    if request.headers.get("HX-Request"):
        return hx_redirect("/login")
    return RedirectResponse("/login", status_code=303)


def hashing_busy_handler(request: Request, exc: HashingBusy) -> Response:
    return form_error(request, "The server is busy. Try again in a moment.", status_code=503)
