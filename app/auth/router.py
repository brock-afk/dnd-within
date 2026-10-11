import secrets
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import OptionalUser
from app.auth.limits import auth_attempts, client_key
from app.auth.models import User
from app.auth.security import HashingBusy, hash_password, verify_password
from app.core.config import settings
from app.core.db import DbSession
from app.core.templates import form_error, hx_redirect, templates

router = APIRouter(tags=["auth"])


TOO_MANY = "Too many attempts. Try again in a few minutes."


def _client(request: Request) -> str:
    # The real address behind Caddy: uvicorn runs with --proxy-headers in production.
    return client_key(request.client.host if request.client else "")


@contextmanager
def _refund_if_busy(key: str):
    """Turned away before anything was checked, so it isn't a guess."""
    try:
        yield
    except HashingBusy:
        auth_attempts.refund(key)
        raise


def _log_in(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html")


@router.post("/login")
def login(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    key = _client(request)
    if not auth_attempts.attempt(key):
        return form_error(request, TOO_MANY, status_code=429)
    user = db.scalar(select(User).where(User.username == username.strip()))
    db.commit()  # hands the connection back to the pool while hashing (may wait for a slot)
    with _refund_if_busy(key):
        valid = verify_password(user.password_hash if user else None, password)
    if not valid:
        return form_error(request, "Invalid username or password.", status_code=401)
    auth_attempts.refund(key)  # only failed guesses count
    _log_in(request, user)
    return hx_redirect("/")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "auth/register.html", {"invite_required": bool(settings.invite_code)}
    )


@router.post("/register")
def register(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    invite_code: Annotated[str, Form()] = "",
):
    # Typos are checked first, so they don't use up attempts.
    username = username.strip()
    if not 3 <= len(username) <= 50:
        return form_error(request, "Username must be 3–50 characters.")
    if len(password) < 8:
        return form_error(request, "Password must be at least 8 characters.")
    if password != confirm_password:
        return form_error(request, "Passwords do not match.")
    key = _client(request)
    if not auth_attempts.attempt(key):
        return form_error(request, TOO_MANY, status_code=429)
    if settings.invite_code and not secrets.compare_digest(
        invite_code.strip().encode(), settings.invite_code.encode()
    ):
        return form_error(request, "That invite code isn't right.", status_code=403)
    taken = db.scalar(select(User.id).where(User.username == username))
    db.commit()  # hands the connection back to the pool while hashing (may wait for a slot)
    if taken:
        return form_error(request, "That username is taken.", status_code=409)

    with _refund_if_busy(key):
        user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # registered by someone else since the check above
        db.rollback()
        return form_error(request, "That username is taken.", status_code=409)
    auth_attempts.refund(key)  # only failed guesses count
    _log_in(request, user)
    return hx_redirect("/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return hx_redirect("/login")
