import pytest

from app.core.forms import parse_id


@pytest.mark.parametrize("raw, expected", [("1", 1), ("0042", 42), ("9" * 18, int("9" * 18))])
def test_parse_id_reads_ascii_digits(raw, expected):
    assert parse_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "-1", "1.5", " 1", "²", "٣", "1" * 19])
def test_parse_id_rejects_anything_else(raw):
    assert parse_id(raw) is None
