import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.auth.dependencies import CurrentUser, OptionalUser
from app.characters.dependencies import OwnedCharacter
from app.characters.page import render_character_page
from app.core.db import DbSession, SessionLocal
from app.sharing.live import subscribe, unsubscribe
from app.sharing.service import make_link, shared_character, stop_sharing
from app.sheet.router import refresh_sheet, render_sheet

router = APIRouter(tags=["sharing"])


def _shared(db: DbSession, token: str):
    character = shared_character(db, token)
    if character is None:
        raise HTTPException(status_code=404)  # never shared, or the link was replaced/stopped
    return character


@router.get("/shared/{token}", response_class=HTMLResponse)
def shared_sheet(request: Request, db: DbSession, user: OptionalUser, token: str):
    """The Play sheet, read-only, for anyone with the link. No login needed."""
    character = _shared(db, token)
    return render_sheet(request, db, user, character, read_only=True, base_url=f"/shared/{token}")


@router.get("/shared/{token}/build", response_class=HTMLResponse)
def shared_build(request: Request, db: DbSession, user: OptionalUser, token: str):
    """The Build page, read-only, for anyone with the link."""
    character = _shared(db, token)
    return render_character_page(
        request, db, user, character, read_only=True, base_url=f"/shared/{token}"
    )


HEARTBEAT_SECONDS = 20  # keeps proxies from closing a quiet stream
STREAM_SECONDS = 600  # then the browser reconnects (EventSource does it by itself)


@router.get("/shared/{token}/events")
async def shared_events(request: Request, token: str):
    """Server-sent events for a shared view: "changed" whenever the owner changes the
    character, so the page refreshes right away (static/live.js)."""
    with SessionLocal() as db:  # short-lived: the stream itself holds no connection
        character = shared_character(db, token)
        if character is None:
            raise HTTPException(status_code=404)
        character_id = character.id

    async def stream():
        queue = subscribe(character_id)
        ends = time.monotonic() + STREAM_SECONDS
        try:
            yield "retry: 2000\n\n"
            while time.monotonic() < ends and not await request.is_disconnected():
                try:
                    await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield "data: changed\n\n"
                except TimeoutError:
                    yield ": still here\n\n"
        finally:
            unsubscribe(character_id, queue)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


@router.post("/characters/{character_id}/share", response_class=HTMLResponse)
def share(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    """Share publicly with a new link, replacing any old one."""
    make_link(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/share/stop", response_class=HTMLResponse)
def stop(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    stop_sharing(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)
