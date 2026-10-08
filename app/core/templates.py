from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent.parent

# Shared templates (base layout, common partials) live in app/templates. Each domain
# keeps its own in app/<domain>/templates/<domain>/, so names are namespaced like
# "auth/login.html" and domains can't collide.
templates = Jinja2Templates(
    directory=[APP_DIR / "templates", *sorted(APP_DIR.glob("*/templates"))]
)


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
