import pytest

from app.core.forms import parse_amount, parse_id, parse_int


@pytest.mark.parametrize("raw, expected", [("1", 1), ("0042", 42), ("9" * 18, int("9" * 18))])
def test_parse_id_reads_ascii_digits(raw, expected):
    assert parse_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "-1", "1.5", " 1", "²", "٣", "1" * 19])
def test_parse_id_rejects_anything_else(raw):
    assert parse_id(raw) is None


@pytest.mark.parametrize("raw, expected", [("3", 3), (" 3 ", 3), ("+3", 3), ("-3", -3), ("−3", -3)])
def test_parse_amount_reads_signed_numbers(raw, expected):
    assert parse_amount(raw, -5, 5) == expected


@pytest.mark.parametrize("raw", ["", "abc", "²", "٣", "３", "1.5", "12345", "6", "-6"])
def test_parse_amount_rejects_anything_else(raw):
    assert parse_amount(raw, -5, 5) is None


@pytest.mark.parametrize("raw, expected", [("100", 100), ("-1", -1), ("x", None), ("12345", None)])
def test_parse_int_checks_only_the_form(raw, expected):
    assert parse_int(raw) == expected


@pytest.mark.parametrize(
    "raw, expected", [("1000000", 1_000_000), ("0005", 5), ("10000000", None), ("²", None)]
)
def test_parse_amount_allows_the_digits_its_bounds_need(raw, expected):
    assert parse_amount(raw, 0, 1_000_000) == expected
