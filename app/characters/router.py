from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.core.db import DbSession
from app.core.templates import form_error, hx_redirect, templates
from app.species.models import Species

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


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request, db: DbSession, user: CurrentUser):
    return templates.TemplateResponse(
        request,
        "characters/new.html",
        {
            "user": user,
            "classes": db.scalars(select(CharacterClass).order_by(CharacterClass.name)).all(),
            "species": db.scalars(select(Species).order_by(Species.name)).all(),
        },
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
    if not 1 <= len(name) <= 60:
        return form_error(request, "Give your character a name (up to 60 characters).")
    if class_id is None or db.get(CharacterClass, class_id) is None:
        return form_error(request, "Choose a class.")
    if species_id is None or db.get(Species, species_id) is None:
        return form_error(request, "Choose a species.")

    db.add(Character(user_id=user.id, name=name, class_id=class_id, species_id=species_id))
    db.commit()
    return hx_redirect("/characters")
