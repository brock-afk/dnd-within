from urllib.parse import urlsplit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_cross_origin(method: str, sec_fetch_site: str | None, origin: str | None, host: str) -> bool:
    if method.upper() in SAFE_METHODS:
        return False
    if sec_fetch_site is not None:
        return sec_fetch_site not in ("same-origin", "none")
    if origin is None:
        return False
    return urlsplit(origin).netloc != host
