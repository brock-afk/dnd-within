from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth.queries import RegisterView
from app.auth.service import Refusal
from app.core.templates import form_error, templates, view_context

STATUS = {
    Refusal.TOO_MANY: 429,
    Refusal.BAD_LOGIN: 401,
    Refusal.BAD_INVITE: 403,
    Refusal.TAKEN: 409,
}


def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "auth/login.html")


def register(request: Request, view: RegisterView) -> HTMLResponse:
    return templates.TemplateResponse(request, "auth/register.html", view_context(view))


def refused(request: Request, error: Refusal | str) -> HTMLResponse:
    if isinstance(error, Refusal):
        return form_error(request, error.value, status_code=STATUS[error])
    return form_error(request, error)
