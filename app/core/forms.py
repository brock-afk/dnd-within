import re


def parse_id(raw: str) -> int | None:
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 18 else None


def _parse_digits(raw: str, digits: int) -> int | None:
    raw = raw.strip().replace("−", "-")
    return int(raw) if re.fullmatch(rf"[+-]?[0-9]{{1,{digits}}}", raw) else None


def parse_int(raw: str) -> int | None:
    return _parse_digits(raw, 4)


def parse_amount(raw: str, low: int, high: int) -> int | None:
    value = _parse_digits(raw, 18)
    return value if value is not None and low <= value <= high else None
