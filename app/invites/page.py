from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import morph_in_place, templates, view_context
from app.invites.models import NOTE_LENGTH
from app.invites.queries import InvitesView
from app.invites.rules import INVITE_LIFETIME


def invites(
    request: Request,
    view: InvitesView,
    form_error: str | None = None,
    list_error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "invites/list.html",
        view_context(
            view,
            form_error=form_error,
            list_error=list_error,
            note_length=NOTE_LENGTH,
            lifetime_days=INVITE_LIFETIME.days,
        ),
        status_code=400 if form_error or list_error else 200,
    )


def created(request: Request, view: InvitesView) -> HTMLResponse:
    return morph_in_place(invites(request, view), "#invites-page")


def form_refused(request: Request, view: InvitesView, error: str) -> HTMLResponse:
    return morph_in_place(invites(request, view, form_error=error), "#invite-form")


def list_refreshed(request: Request, view: InvitesView, error: str | None) -> HTMLResponse:
    return morph_in_place(invites(request, view, list_error=error), "#invite-list")
