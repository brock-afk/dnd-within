from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth.queries import RegisterView
from app.auth.service import BAD_INVITE, BAD_LOGIN, TAKEN, TOO_MANY
from app.core.templates import form_error, templates, view_context

STATUS = {TOO_MANY: 429, BAD_LOGIN: 401, BAD_INVITE: 403, TAKEN: 409}


def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "auth/login.html")


def register(request: Request, view: RegisterView) -> HTMLResponse:
    return templates.TemplateResponse(request, "auth/register.html", view_context(view))


def refused(request: Request, error: str) -> HTMLResponse:
    return form_error(request, error, status_code=STATUS.get(error, 400))
