from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import AdminUser, get_admin
from app.core.db import DbSession
from app.invites import page
from app.invites.dependencies import InviteRow
from app.invites.form import InviteForm
from app.invites.queries import invites_view
from app.invites.service import create_from_form, revoke

router = APIRouter(prefix="/admin", tags=["invites"], dependencies=[Depends(get_admin)])


@router.get("/invites", response_class=HTMLResponse)
def list_invites(request: Request, db: DbSession, admin: AdminUser):
    return page.invites(request, invites_view(db, admin))


@router.post("/invites", response_class=HTMLResponse)
def create(request: Request, db: DbSession, admin: AdminUser, form: Annotated[InviteForm, Form()]):
    created = create_from_form(db, form)
    if isinstance(created, str):
        return page.form_refused(request, invites_view(db, admin, note=form.note), created)
    return page.created(request, invites_view(db, admin, created))


@router.post("/invites/{invite_id}/revoke", response_class=HTMLResponse)
def revoke_invite(request: Request, db: DbSession, admin: AdminUser, invite: InviteRow):
    error = revoke(db, invite)
    return page.list_refreshed(request, invites_view(db, admin), error)
