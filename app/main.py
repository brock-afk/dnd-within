from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (registers every table, so relationships resolve)
from app.abilities.router import router as abilities_router
from app.auth.dependencies import LoginRequired, login_required_handler
from app.auth.router import router as auth_router
from app.characters.router import router as characters_router
from app.classes.data import CLASS_FEATURES, CLASSES, SUBCLASS_FEATURES, SUBCLASSES
from app.classes.models import CharacterClass
from app.classes.sync import subclass_ids, sync_subclasses
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.reference_data import sync_reference_rows
from app.core.templates import APP_DIR
from app.features.router import router as features_router
from app.features.sync import sync_features
from app.leveling.router import router as leveling_router
from app.skills.data import SKILLS
from app.skills.models import Skill
from app.species.data import SPECIES, SPECIES_FEATURES
from app.species.models import Species
from app.spells.data import SPELLS
from app.spells.sync import sync_spells


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema itself is managed by Alembic (run on container start); this only syncs content.
    with SessionLocal() as db:
        sync_reference_rows(db, CharacterClass, CLASSES)
        sync_reference_rows(db, Species, SPECIES)
        sync_reference_rows(db, Skill, SKILLS)
        sync_spells(db, SPELLS)
        sync_subclasses(db, SUBCLASSES)

        class_ids = {c.slug: c.id for c in db.scalars(select(CharacterClass))}
        species_ids = {s.slug: s.id for s in db.scalars(select(Species))}
        sub_ids = subclass_ids(db)
        sync_features(db, "class_id", {class_ids[k]: v for k, v in CLASS_FEATURES.items()})
        sync_features(db, "species_id", {species_ids[k]: v for k, v in SPECIES_FEATURES.items()})
        sync_features(db, "subclass_id", {sub_ids[k]: v for k, v in SUBCLASS_FEATURES.items()})
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
app.include_router(abilities_router)
app.include_router(leveling_router)
