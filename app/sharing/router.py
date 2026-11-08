import asyncio
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.auth.dependencies import CurrentUser, OptionalUser
from app.characters.dependencies import OwnedCharacter
from app.characters.page import build_page
from app.characters.queries import build_page_view
from app.core.db import DbSession
from app.sharing.dependencies import SharedCharacter
from app.sharing.live import subscribe, unsubscribe
from app.sharing.service import make_link, stop_sharing
from app.sheet import page as sheet_page
from app.sheet.queries import refreshed_sheet_view, sheet_view

router = APIRouter(tags=["sharing"])


@router.get("/shared/{token}", response_class=HTMLResponse)
def shared_sheet(
    request: Request, db: DbSession, user: OptionalUser, character: SharedCharacter, token: str
):
    return sheet_page.sheet(
        request, sheet_view(db, user, character, read_only=True, base_url=f"/shared/{token}")
    )


@router.get("/shared/{token}/build", response_class=HTMLResponse)
def shared_build(
    request: Request, db: DbSession, user: OptionalUser, character: SharedCharacter, token: str
):
    view = build_page_view(db, user, character, read_only=True, base_url=f"/shared/{token}")
    return build_page(request, view)


HEARTBEAT_SECONDS = 20
STREAM_SECONDS = 600


@router.get("/shared/{token}/events")
async def shared_events(request: Request, character: SharedCharacter):
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
    make_link(db, character)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.post("/characters/{character_id}/share/stop", response_class=HTMLResponse)
def stop(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    stop_sharing(db, character)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))
