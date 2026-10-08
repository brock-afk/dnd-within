from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import Base, engine, get_db
from app.models import User
from app.security import hash_password, verify_password

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine while there's only one table; switch to Alembic migrations as the schema grows.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.session_https_only,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

DbSession = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def form_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/form_error.html", {"message": message}, status_code=status_code
    )


def redirect(path: str) -> Response:
    # htmx follows HX-Redirect with a full page load.
    return Response(status_code=200, headers={"HX-Redirect": path})


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: DbSession):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "home.html", {"user": user})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.post("/login")
def login(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not verify_password(user.password_hash if user else None, password):
        return form_error(request, "Invalid username or password.", status_code=401)
    request.session.clear()
    request.session["user_id"] = user.id
    return redirect("/")


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@app.post("/register")
def register(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
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
    request.session.clear()
    request.session["user_id"] = user.id
    return redirect("/")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")
