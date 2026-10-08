from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import models as auth_models  # noqa: F401  (registers tables with Base)
from app.auth.dependencies import LoginRequired, login_required_handler
from app.auth.router import router as auth_router
from app.characters import models as character_models  # noqa: F401
from app.characters.router import router as characters_router
from app.classes.data import CLASSES
from app.classes.models import CharacterClass
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.reference_data import sync_reference_rows
from app.core.templates import APP_DIR
from app.species.data import SPECIES
from app.species.models import Species


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fine while the schema is small; switch to Alembic migrations as it grows.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_reference_rows(db, CharacterClass, CLASSES)
        sync_reference_rows(db, Species, SPECIES)
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
