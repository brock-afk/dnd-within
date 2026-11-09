import re

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401
from app.abilities.router import router as abilities_router
from app.auth.dependencies import LoginRequired, hashing_busy_handler, login_required_handler
from app.auth.router import router as auth_router
from app.auth.security import HashingBusy
from app.backgrounds.router import router as backgrounds_router
from app.characters.router import router as characters_router
from app.core.config import settings
from app.core.csrf import is_cross_origin
from app.core.db import DbSession
from app.core.templates import APP_DIR, templates
from app.features.router import router as features_router
from app.homebrew.router import router as homebrew_router
from app.inventory.router import router as inventory_router
from app.inventory.rules import Coin, CoinChange
from app.invites.router import router as invites_router
from app.leveling.router import router as leveling_router
from app.sharing.live import publish, publish_all
from app.sharing.router import router as sharing_router
from app.sheet.router import router as sheet_router
from app.species.router import router as species_router

app = FastAPI()
templates.env.globals.update(Coin=Coin, CoinChange=CoinChange)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.session_https_only,
)
app.add_exception_handler(LoginRequired, login_required_handler)
app.add_exception_handler(HashingBusy, hashing_busy_handler)


@app.middleware("http")
async def refuse_cross_origin(request: Request, call_next):
    h = request.headers
    if is_cross_origin(request.method, h.get("sec-fetch-site"), h.get("origin"), h.get("host", "")):
        return PlainTextResponse("Cross-origin request refused.", status_code=403)
    return await call_next(request)


CHARACTER_PATH = re.compile(r"^/characters/(\d+)/")


@app.middleware("http")
async def notify_shared_views(request: Request, call_next):
    response = await call_next(request)
    if request.method != "GET" and response.status_code < 400:
        if match := CHARACTER_PATH.match(request.url.path):
            publish(int(match[1]))
        elif request.url.path.startswith("/homebrew/"):
            publish_all()
    return response


@app.get("/healthz", include_in_schema=False)
def healthz(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return PlainTextResponse("database unavailable", status_code=503)
    return PlainTextResponse("ok")


app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.include_router(auth_router)
app.include_router(characters_router)
app.include_router(features_router)
app.include_router(backgrounds_router)
app.include_router(species_router)
app.include_router(abilities_router)
app.include_router(leveling_router)
app.include_router(sheet_router)
app.include_router(inventory_router)
app.include_router(homebrew_router)
app.include_router(sharing_router)
app.include_router(invites_router)
