from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.core.db import DbSession
from app.core.templates import hx_redirect, templates
from app.features.service import class_features, species_features
from app.skills.queries import character_skills
from app.species.models import Species
from app.spells.queries import character_spells

router = APIRouter(tags=["characters"])


@router.get("/")
def index():
    return RedirectResponse("/characters", status_code=303)


@router.get("/characters", response_class=HTMLResponse)
def list_characters(request: Request, db: DbSession, user: CurrentUser):
    characters = db.scalars(
        select(Character).where(Character.user_id == user.id).order_by(Character.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request, "characters/list.html", {"user": user, "characters": characters}
    )


def _form_options(db: DbSession) -> dict:
    return {
        "classes": db.scalars(select(CharacterClass).order_by(CharacterClass.name)).all(),
        "species": db.scalars(select(Species).order_by(Species.name)).all(),
    }


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request, db: DbSession, user: CurrentUser):
    return templates.TemplateResponse(
        request, "characters/new.html", {"user": user, **_form_options(db)}
    )


@router.post("/characters")
def create_character(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    name: Annotated[str, Form()] = "",
    class_id: Annotated[int | None, Form()] = None,
    species_id: Annotated[int | None, Form()] = None,
):
    name = name.strip()
    errors = {}
    if not name:
        errors["name"] = "Give your character a name."
    elif len(name) > 60:
        errors["name"] = "Names can be at most 60 characters."
    if class_id is None or db.get(CharacterClass, class_id) is None:
        errors["class_id"] = "Choose a class."
    if species_id is None or db.get(Species, species_id) is None:
        errors["species_id"] = "Choose a species."

    if errors:
        # Re-render the whole form so every problem shows next to its field,
        # with the user's entries kept.
        return templates.TemplateResponse(
            request,
            "characters/partials/form.html",
            {
                "errors": errors,
                "values": {"name": name, "class_id": class_id, "species_id": species_id},
                **_form_options(db),
            },
            status_code=400,
        )

    character = Character(user_id=user.id, name=name, class_id=class_id, species_id=species_id)
    db.add(character)
    db.commit()
    return hx_redirect(f"/characters/{character.id}")


@router.get("/characters/{character_id}", response_class=HTMLResponse)
def show_character(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    species_feats = species_features(db, character)
    class_feats = class_features(db, character)
    pending = [cv for fv in species_feats + class_feats for cv in fv.choices if not cv.done]
    return templates.TemplateResponse(
        request,
        "characters/show.html",
        {
            "user": user,
            "character": character,
            "species_features": species_feats,
            "class_features": class_feats,
            "pending": pending,
            "skills": character_skills(db, character.id),
            "spells": character_spells(db, character.id),
        },
    )
