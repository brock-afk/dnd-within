"""Blocking cross-site requests that change things (CSRF), from the headers browsers send.
The same checks as Go's net/http CrossOriginProtection, so no tokens in forms."""

from urllib.parse import urlsplit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_cross_origin(method: str, sec_fetch_site: str | None, origin: str | None, host: str) -> bool:
    """Whether a request comes from another site and must be refused.

    - Safe methods never change anything, so they're always allowed.
    - Sec-Fetch-Site (all current browsers): only "same-origin", or "none" (the user's own
      action, like a bookmark). "same-site" is refused too: a sibling subdomain isn't this app.
    - Older browsers: the Origin header's host must be this one.
    - Neither header: not a browser (curl, scripts), which can't carry a victim's cookie."""
    if method.upper() in SAFE_METHODS:
        return False
    if sec_fetch_site is not None:
        return sec_fetch_site not in ("same-origin", "none")
    if origin is None:
        return False
    return urlsplit(origin).netloc != host
