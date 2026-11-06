"""Reading values that arrive as form or query strings."""

import re


def parse_id(raw: str) -> int | None:
    """A row id, or None. isdigit() alone isn't enough before int(): it accepts digits int()
    rejects (superscripts like "²") and strings too long to convert."""
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 18 else None


def parse_int(raw: str) -> int | None:
    """A whole number of up to four digits, or None. Accepts a leading "+", and "−" (the minus
    sign shown in placeholders) as well as "-". ASCII digits only, like parse_id."""
    raw = raw.strip().replace("−", "-")
    return int(raw) if re.fullmatch(r"[+-]?[0-9]{1,4}", raw) else None


def parse_amount(raw: str, low: int, high: int) -> int | None:
    """parse_int, within [low, high]."""
    value = parse_int(raw)
    return value if value is not None and low <= value <= high else None
