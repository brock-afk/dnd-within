from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (registers every table, so relationships resolve)
from app.abilities.router import router as abilities_router
from app.auth.dependencies import LoginRequired, login_required_handler
from app.auth.router import router as auth_router
from app.backgrounds.router import router as backgrounds_router
from app.characters.router import router as characters_router
from app.content.importer import import_packs
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.templates import APP_DIR
from app.features.router import router as features_router
from app.homebrew.router import router as homebrew_router
from app.inventory.router import router as inventory_router
from app.leveling.router import router as leveling_router
from app.sharing.router import router as sharing_router
from app.sheet.router import router as sheet_router
from app.species.router import router as species_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic (run on container start). Content comes from the
    # packs in CONTENT_PATHS; only packs whose files changed are imported.
    with SessionLocal() as db:
        import_packs(db)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.session_https_only,
)
app.add_exception_handler(LoginRequired, login_required_handler)
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
