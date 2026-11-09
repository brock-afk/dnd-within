import re
from datetime import datetime

import pytest
from sqlalchemy import select

from app.invites.models import Invite
from app.invites.router import router
from app.invites.rules import InviteStatus, code_hash, status
from app.invites.service import claim, create_invite, revoke


def test_an_invite_stores_only_the_hash_of_its_code(db):
    invite, code = create_invite(db, "Alex")
    stored = db.execute(select(Invite.__table__).where(Invite.id == invite.id)).one()
    assert code not in stored
    assert invite.code_hash == code_hash(code)


def test_an_invite_is_claimed_once(db, invite, owner, other_user):
    _, code = invite
    assert claim(db, code, owner)
    assert not claim(db, code, other_user)


def test_only_an_active_invite_can_be_revoked(db, invite, owner):
    row, code = invite
    assert revoke(db, row) is None
    db.refresh(row)
    assert status(row, datetime.now()) is InviteStatus.REVOKED
    assert not claim(db, code, owner)
    assert revoke(db, row) == "Only an active invite can be revoked."


ROUTES = [(method, route.path) for route in router.routes for method in route.methods]


@pytest.fixture
def admin_client(db, owner, client):
    owner.is_admin = True
    db.flush()
    return client


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_only_an_admin_reaches_the_invite_routes(visitor, client, method, path):
    path = path.replace("{invite_id}", "1")
    assert visitor.request(method, path).status_code == 404
    assert client.request(method, path).status_code == 404


def test_only_an_admin_sees_the_invites_link(client, db, owner):
    assert "/admin/invites" not in client.get("/characters").text
    owner.is_admin = True
    assert "/admin/invites" in client.get("/characters").text


def test_inviting_someone_through_the_app(admin_client, visitor):
    blank = admin_client.post("/admin/invites", data={"note": "  "})
    assert (blank.status_code, blank.headers["HX-Retarget"]) == (400, "#invite-form")
    created = admin_client.post("/admin/invites", data={"note": "Alex"})
    code = re.search(r'register#invite=([\w-]+)"', created.text)[1]
    new = {"username": "newcomer", "password": "long enough", "confirm_password": "long enough"}
    registered = visitor.post("/register", data=new | {"invite_code": code})
    assert registered.headers["HX-Redirect"] == "/"
    listed = admin_client.get("/admin/invites").text
    assert "used by newcomer" in listed
    assert code not in listed


def test_revoking_through_the_app(admin_client, invite):
    row, _ = invite
    revoked = admin_client.post(f"/admin/invites/{row.id}/revoke")
    assert revoked.headers["HX-Retarget"] == "#invite-list"
    assert "Revoked" in revoked.text
    again = admin_client.post(f"/admin/invites/{row.id}/revoke")
    assert again.status_code == 400
    assert "Only an active invite can be revoked." in again.text
