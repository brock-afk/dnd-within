"""Reading values that arrive as form or query strings."""


def parse_id(raw: str) -> int | None:
    """A row id, or None. isdigit() alone isn't enough before int(): it accepts digits int()
    rejects (superscripts like "²") and strings too long to convert."""
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 18 else None
