from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth import page, service
from app.auth.dependencies import ClientThrottle, OptionalUser, end_session, start_session
from app.auth.form import LoginForm, RegisterForm
from app.auth.models import User
from app.auth.service import Refusal
from app.core.db import DbSession
from app.core.templates import hx_redirect

router = APIRouter(tags=["auth"])


def _signed_in(request: Request, outcome: User | Refusal | str) -> Response:
    if not isinstance(outcome, User):
        return page.refused(request, outcome)
    start_session(request, outcome)
    return hx_redirect("/")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return page.login(request)


@router.post("/login")
def login(
    request: Request,
    db: DbSession,
    throttle: ClientThrottle,
    form: Annotated[LoginForm, Form()],
):
    return _signed_in(request, service.log_in(db, form, throttle))


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/", status_code=303)
    return page.register(request)


@router.post("/register")
def register(
    request: Request,
    db: DbSession,
    throttle: ClientThrottle,
    form: Annotated[RegisterForm, Form()],
):
    return _signed_in(request, service.register(db, form, throttle))


@router.post("/logout")
def logout(request: Request):
    end_session(request)
    return hx_redirect("/login")
