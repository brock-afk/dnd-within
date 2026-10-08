from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.classes.models import CharacterClass, CharacterClassLevel
from app.core.db import DbSession
from app.core.templates import hx_redirect, templates
from app.features.service import feature_groups
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


def _name_error(name: str) -> str | None:
    """Validation shared by creating and renaming. Expects an already-stripped name."""
    if not name:
        return "Give your character a name."
    if len(name) > 60:
        return "Names can be at most 60 characters."
    return None


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
    if error := _name_error(name):
        errors["name"] = error
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

    character = Character(
        user_id=user.id,
        name=name,
        species_id=species_id,
        classes=[CharacterClassLevel(class_id=class_id, level=1, position=0)],
    )
    db.add(character)
    db.commit()
    return hx_redirect(f"/characters/{character.id}")


@router.get("/characters/{character_id}", response_class=HTMLResponse)
def show_character(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    groups = feature_groups(db, character)
    pending = [cv for g in groups for fv in g.features for cv in fv.choices if not cv.done]
    return templates.TemplateResponse(
        request,
        "characters/show.html",
        {
            "user": user,
            "character": character,
            "feature_groups": groups,
            "pending": pending,
            "skills": character_skills(db, character.id),
            "spells": character_spells(db, character.id),
        },
    )


def _name_heading(request: Request, character: Character) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "characters/partials/name_heading.html", {"character": character}
    )


@router.get("/characters/{character_id}/name", response_class=HTMLResponse)
def name_heading(request: Request, character: OwnedCharacter):
    return _name_heading(request, character)


@router.get("/characters/{character_id}/name/edit", response_class=HTMLResponse)
def edit_name(request: Request, character: OwnedCharacter):
    return templates.TemplateResponse(
        request,
        "characters/partials/name_form.html",
        {"character": character, "value": character.name},
    )


@router.post("/characters/{character_id}/name", response_class=HTMLResponse)
def rename_character(
    request: Request, db: DbSession, character: OwnedCharacter, name: Annotated[str, Form()] = ""
):
    name = name.strip()
    if error := _name_error(name):
        return templates.TemplateResponse(
            request,
            "characters/partials/name_form.html",
            {"character": character, "value": name, "error": error},
            status_code=400,
        )
    character.name = name
    db.commit()
    return _name_heading(request, character)
