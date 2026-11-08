import threading

import pytest
from sqlalchemy import func, select

from app.auth import security, service
from app.auth.form import LoginForm, RegisterForm
from app.auth.limits import AttemptLimiter, Throttle
from app.auth.models import User
from app.auth.page import STATUS
from app.auth.queries import user_named
from app.auth.security import HashingBusy, verify_password
from app.auth.service import Refusal
from app.core.config import settings

NEW = {"username": "newcomer", "password": "long enough", "confirm_password": "long enough"}


@pytest.fixture
def throttle() -> Throttle:
    return Throttle(AttemptLimiter(limit=2, window=60), "k")


def _attempts_left(throttle: Throttle) -> int:
    left = 0
    while throttle.attempt():
        left += 1
    return left


def _users(db) -> int:
    return db.scalar(select(func.count()).select_from(User))


def test_logging_in_returns_the_user_and_refunds_only_itself(db, owner, password, throttle):
    service.log_in(db, LoginForm(username=owner.username, password="wrong"), throttle)
    form = LoginForm(username=f" {owner.username} ", password=password)
    assert service.log_in(db, form, throttle) is owner
    assert _attempts_left(throttle) == 1


@pytest.mark.parametrize("known", [True, False], ids=["wrong password", "unknown user"])
def test_a_wrong_password_and_an_unknown_user_are_refused_alike(db, owner, throttle, known):
    username = owner.username if known else "nobody"
    form = LoginForm(username=username, password="wrong")
    assert service.log_in(db, form, throttle) is Refusal.BAD_LOGIN
    assert _attempts_left(throttle) == 1


def test_logging_in_past_the_limit_is_refused(db, owner, password, throttle):
    for _ in range(2):
        service.log_in(db, LoginForm(username=owner.username, password="wrong"), throttle)
    form = LoginForm(username=owner.username, password=password)
    assert service.log_in(db, form, throttle) is Refusal.TOO_MANY


def test_a_busy_hasher_gives_the_attempt_back(db, owner, password, throttle, monkeypatch):
    monkeypatch.setattr(security, "_slots", threading.BoundedSemaphore(0))
    monkeypatch.setattr(security, "SLOT_WAIT_SECONDS", 0.01)
    with pytest.raises(HashingBusy):
        service.log_in(db, LoginForm(username=owner.username, password=password), throttle)
    assert _attempts_left(throttle) == 2


@pytest.mark.parametrize("fields", [{"password": ""}, {"username": "  "}])
def test_a_blank_login_uses_no_attempt(db, owner, password, throttle, fields):
    form = LoginForm(**{"username": owner.username, "password": password} | fields)
    assert service.log_in(db, form, throttle) == "Enter your username and password."
    assert _attempts_left(throttle) == 2


def test_every_refusal_has_a_status():
    assert set(STATUS) == set(Refusal)


def test_registering_creates_the_user(db, throttle):
    user = service.register(db, RegisterForm(**NEW), throttle)
    assert user_named(db, "newcomer") is user
    assert verify_password(user.password_hash, "long enough")
    assert _attempts_left(throttle) == 2


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"username": "ab"}, "Username must be 3–50 characters."),
        ({"username": "x" * 51}, "Username must be 3–50 characters."),
        (
            {"password": "short", "confirm_password": "short"},
            "Password must be at least 8 characters.",
        ),
        ({"confirm_password": "different"}, "Passwords do not match."),
    ],
)
def test_a_bad_registration_form_uses_no_attempt(db, throttle, fields, message):
    assert service.register(db, RegisterForm(**NEW | fields), throttle) == message
    assert _attempts_left(throttle) == 2


def test_registering_needs_the_invite_code(db, throttle, monkeypatch):
    monkeypatch.setattr(settings, "invite_code", "friends")
    before = _users(db)
    form = RegisterForm(**NEW, invite_code="guess")
    assert service.register(db, form, throttle) is Refusal.BAD_INVITE
    assert _users(db) == before
    user = service.register(db, RegisterForm(**NEW, invite_code=" friends "), throttle)
    assert isinstance(user, User)


def test_a_taken_username_is_refused(db, owner, throttle):
    before = _users(db)
    form = RegisterForm(**NEW | {"username": owner.username})
    assert service.register(db, form, throttle) is Refusal.TAKEN
    assert _users(db) == before


def test_creating_a_taken_username_leaves_the_session_usable(db, owner):
    assert service.create_user(db, owner.username, "x") is None
    assert service.create_user(db, "another", "x") is not None
    assert user_named(db, "another") is not None


def test_the_pages_open_logged_out_and_redirect_logged_in(visitor, client, monkeypatch):
    assert visitor.get("/login").status_code == 200
    assert 'name="invite_code"' not in visitor.get("/register").text
    monkeypatch.setattr(settings, "invite_code", "friends")
    assert 'name="invite_code"' in visitor.get("/register").text
    for path in ("/login", "/register"):
        response = client.get(path, follow_redirects=False)
        assert (response.status_code, response.headers["location"]) == (303, "/")


def test_logging_in_through_the_app(db, owner, password, visitor):
    refused = visitor.post("/login", data={"username": owner.username, "password": "wrong"})
    assert refused.status_code == 401
    assert Refusal.BAD_LOGIN.value in refused.text
    response = visitor.post("/login", data={"username": owner.username, "password": password})
    assert response.headers["HX-Redirect"] == "/"
    assert visitor.get("/characters").status_code == 200


def test_registering_through_the_app_logs_in(db, visitor):
    response = visitor.post("/register", data=NEW)
    assert response.headers["HX-Redirect"] == "/"
    assert visitor.get("/characters").status_code == 200
    assert user_named(db, "newcomer") is not None


@pytest.mark.parametrize(
    ("path", "status", "message"),
    [
        ("/login", 400, "Enter your username and password."),
        ("/register", 400, "Password must be at least 8 characters."),
    ],
)
def test_a_missing_field_gets_a_message(owner, visitor, path, status, message):
    response = visitor.post(path, data={"username": owner.username})
    assert response.status_code == status
    assert response.text.strip() == f'<p class="error">{message}</p>'


def test_logging_out(client):
    assert client.post("/logout").headers["HX-Redirect"] == "/login"
    response = client.get("/characters", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/login")
    htmx = client.get("/characters", headers={"HX-Request": "true"})
    assert htmx.headers["HX-Redirect"] == "/login"


def test_the_app_turns_away_guesses_past_the_limit(owner, visitor):
    guess = {"username": owner.username, "password": "wrong"}
    statuses = [visitor.post("/login", data=guess).status_code for _ in range(11)]
    assert statuses == [401] * 10 + [429]
