import pytest

from app.core.csrf import is_cross_origin

HOST = "dnd.example.com"


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_always_pass(method):
    assert not is_cross_origin(method, "cross-site", "https://evil.example", HOST)


@pytest.mark.parametrize(
    "site, refused",
    [("same-origin", False), ("none", False), ("same-site", True), ("cross-site", True)],
)
def test_sec_fetch_site_decides_when_sent(site, refused):
    # Takes precedence over Origin, even a matching one.
    assert is_cross_origin("POST", site, f"https://{HOST}", HOST) is refused


@pytest.mark.parametrize(
    "origin, refused",
    [
        (f"https://{HOST}", False),
        ("https://evil.example", True),
        (f"https://sub.{HOST}", True),
        ("null", True),  # sandboxed iframes and some redirects
    ],
)
def test_origin_must_match_host_without_sec_fetch_site(origin, refused):
    assert is_cross_origin("POST", None, origin, HOST) is refused


def test_origin_compares_port():
    assert not is_cross_origin("POST", None, "http://127.0.0.1:8000", "127.0.0.1:8000")
    assert is_cross_origin("POST", None, "http://127.0.0.1:9000", "127.0.0.1:8000")


def test_no_browser_headers_pass():
    # curl and scripts: no victim browser, so no stolen cookie to ride on.
    assert not is_cross_origin("POST", None, None, HOST)
