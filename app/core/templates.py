import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent.parent

# Shared templates (base layout, common partials) live in app/templates. Each domain
# keeps its own in app/<domain>/templates/<domain>/, so names are namespaced like
# "auth/login.html" and domains can't collide.
templates = Jinja2Templates(directory=[APP_DIR / "templates", *sorted(APP_DIR.glob("*/templates"))])

_static_versions: dict[str, tuple[float, str]] = {}


def static_url(path: str) -> str:
    """/static/<path>?v=<content hash>. The URL changes whenever the file does, so browsers
    never keep running a stale cached script or stylesheet. Hashes are cached per file and
    recomputed only when its modification time changes."""
    file = APP_DIR / "static" / path
    mtime = file.stat().st_mtime
    cached = _static_versions.get(path)
    if cached is None or cached[0] != mtime:
        cached = (mtime, hashlib.sha256(file.read_bytes()).hexdigest()[:10])
        _static_versions[path] = cached
    return f"/static/{path}?v={cached[1]}"


templates.env.globals["static_url"] = static_url


def form_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/form_error.html", {"message": message}, status_code=status_code
    )


def hx_redirect(path: str) -> Response:
    # htmx follows HX-Redirect with a full page load.
    return Response(status_code=200, headers={"HX-Redirect": path})


def morph_in_place(response: Response, selector: str) -> Response:
    """Tell htmx to morph just `selector` from this full-page response into the current page,
    whatever element sent the request. Unchanged parts stay put, so the scroll position and
    focus are kept, unlike a redirect."""
    response.headers["HX-Retarget"] = selector
    response.headers["HX-Reswap"] = "outerMorph"
    response.headers["HX-Reselect"] = selector
    return response
