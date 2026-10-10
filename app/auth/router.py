import secrets
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import OptionalUser
from app.auth.models import User
from app.auth.security import hash_password, verify_password
from app.core.config import settings
from app.core.db import DbSession
from app.core.templates import form_error, hx_redirect, templates

router = APIRouter(tags=["auth"])


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
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not verify_password(user.password_hash if user else None, password):
        return form_error(request, "Invalid username or password.", status_code=401)
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
    if settings.invite_code and not secrets.compare_digest(
        invite_code.strip().encode(), settings.invite_code.encode()
    ):
        return form_error(request, "That invite code isn't right.", status_code=403)
    username = username.strip()
    if not 3 <= len(username) <= 50:
        return form_error(request, "Username must be 3–50 characters.")
    if len(password) < 8:
        return form_error(request, "Password must be at least 8 characters.")
    if password != confirm_password:
        return form_error(request, "Passwords do not match.")
    if db.scalar(select(User.id).where(User.username == username)):
        return form_error(request, "That username is taken.", status_code=409)

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    _log_in(request, user)
    return hx_redirect("/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return hx_redirect("/login")
