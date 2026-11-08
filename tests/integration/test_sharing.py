import pytest

from app.sharing.queries import public_share, shared_character
from app.sharing.service import make_link, stop_sharing


def test_anyone_with_the_link_sees_the_pages_read_only(db, character, visitor):
    token = make_link(db, character).token
    db.commit()
    for page in (visitor.get(f"/shared/{token}"), visitor.get(f"/shared/{token}/build")):
        assert page.status_code == 200
        assert character.name in page.text
        assert "live.js" in page.text
        assert 'id="share-menu"' not in page.text
        assert "hx-post" not in page.text


@pytest.mark.parametrize("path", ["", "/build", "/events"])
def test_a_dead_link_is_not_found(db, character, visitor, path):
    replaced = make_link(db, character).token
    stopped = make_link(db, character).token
    stop_sharing(db, character)
    db.commit()
    for token in ("never-made", replaced, stopped):
        assert visitor.get(f"/shared/{token}{path}").status_code == 404


def test_the_owner_shares_and_stops(db, character, client):
    shared = client.post(f"/characters/{character.id}/share")
    assert shared.status_code == 200
    share = public_share(db, character)
    assert f"/shared/{share.token}" in shared.text

    stopped = client.post(f"/characters/{character.id}/share/stop")
    assert stopped.status_code == 200
    assert public_share(db, character) is None
    assert "Share publicly" in stopped.text


@pytest.mark.parametrize("path", ["/share", "/share/stop"])
def test_only_the_owner_can_share(db, theirs, client, path):
    token = make_link(db, theirs).token
    db.commit()
    assert client.post(f"/characters/{theirs.id}{path}").status_code == 404
    assert shared_character(db, token) is theirs
