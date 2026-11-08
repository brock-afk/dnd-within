import hashlib
from dataclasses import fields
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(directory=[APP_DIR / "templates", *sorted(APP_DIR.glob("*/templates"))])

_static_versions: dict[str, tuple[float, str]] = {}


def static_url(path: str) -> str:
    file = APP_DIR / "static" / path
    mtime = file.stat().st_mtime
    cached = _static_versions.get(path)
    if cached is None or cached[0] != mtime:
        cached = (mtime, hashlib.sha256(file.read_bytes()).hexdigest()[:10])
        _static_versions[path] = cached
    return f"/static/{path}?v={cached[1]}"


templates.env.globals["static_url"] = static_url


def view_context(view, **extra) -> dict:
    return {f.name: getattr(view, f.name) for f in fields(view)} | extra


def form_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/form_error.html", {"message": message}, status_code=status_code
    )


def hx_redirect(path: str) -> Response:
    return Response(status_code=200, headers={"HX-Redirect": path})


def morph_in_place(response: Response, selector: str) -> Response:
    response.headers["HX-Retarget"] = selector
    response.headers["HX-Reswap"] = "outerMorph"
    response.headers["HX-Reselect"] = selector
    return response
