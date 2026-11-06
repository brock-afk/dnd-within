"""Reading values that arrive as form or query strings."""

import re


def parse_id(raw: str) -> int | None:
    """A row id, or None. isdigit() alone isn't enough before int(): it accepts digits int()
    rejects (superscripts like "²") and strings too long to convert."""
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 18 else None


def parse_amount(raw: str, low: int, high: int) -> int | None:
    """A whole number in [low, high]. Accepts a leading "+", and "−" (the minus sign shown in
    placeholders) as well as "-". ASCII digits only, like parse_id."""
    raw = raw.strip().replace("−", "-")
    if re.fullmatch(r"[+-]?[0-9]{1,4}", raw) and low <= int(raw) <= high:
        return int(raw)
    return None
