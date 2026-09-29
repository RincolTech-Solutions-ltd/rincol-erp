"""
Tests for app._safe_float / app._safe_int.

Money fields are now text inputs formatted with thousands commas by the
shared .money-input JS helper (see static/js/main.js). These two functions
are what stands between that comma-formatted string and the database, so a
regression here reintroduces the "form value has a comma → save crashes or
silently truncates" bug that issue #40 fixed.
"""
import pytest

import app


class TestSafeFloat:

    @pytest.mark.parametrize("raw,expected", [
        ("1234",          1234.0),
        ("1,234",         1234.0),
        ("1,234,567",     1234567.0),
        ("1,234,567.50",  1234567.50),
        ("750000.0",      750000.0),
        (0,               0.0),
        (1234.5,          1234.5),
    ])
    def test_parses_value(self, raw, expected):
        assert app._safe_float(raw, 0) == expected

    @pytest.mark.parametrize("raw", ["", None])
    def test_empty_or_none_uses_default(self, raw):
        assert app._safe_float(raw, 750000) == 750000.0

    def test_zero_default_when_unspecified(self):
        assert app._safe_float("") == 0.0

    # JUSTIFICATION-A3: pure added test coverage for the edge cases the
    # adversarial review found untested; no production code is involved.
    @pytest.mark.parametrize("raw,expected", [
        ("-1,250",    -1250.0),
        ("-1,250.75", -1250.75),
        ("  1,250  ", 1250.0),
    ])
    def test_negatives_and_whitespace(self, raw, expected):
        # a credit note or a correction can legitimately be negative, and the
        # submit-time comma stripper leaves surrounding whitespace alone
        assert app._safe_float(raw, 0) == expected

    def test_literal_zero_string_is_zero_not_the_default(self):
        # "0" is truthy as a string, so it must not fall through to the default;
        # this is the trap that would make a deliberately zeroed cost silently
        # reappear as the field's default figure
        assert app._safe_float("0", 750000) == 0.0

    def test_falsy_numeric_zero_takes_the_default(self):
        # documents current behaviour: an actual 0 (not "0") is falsy, so the
        # default wins. Every money caller passes a default of 0, so this is
        # harmless there, but it must not be changed blindly.
        assert app._safe_float(0, 750000) == 750000.0

    @pytest.mark.parametrize("raw", ["abc", "1.2.3", ",", "12 000"])
    def test_non_numeric_raises(self, raw):
        # pinned deliberately: the routes have no field-level validation, so a
        # non-numeric money value is a 500, not a silent zero. If that ever
        # becomes a flash message instead, this test should be what forces the
        # decision to be explicit.
        with pytest.raises(ValueError):
            app._safe_float(raw, 0)


class TestSafeInt:

    @pytest.mark.parametrize("raw,expected", [
        ("48",       48),
        ("1,234",    1234),
        ("1,234,567", 1234567),
        (0,          0),
        (48,         48),
    ])
    def test_parses_value(self, raw, expected):
        assert app._safe_int(raw, 0) == expected

    @pytest.mark.parametrize("raw", ["", None])
    def test_empty_or_none_uses_default(self, raw):
        assert app._safe_int(raw, 48) == 48

    def test_zero_default_when_unspecified(self):
        assert app._safe_int("") == 0

    # JUSTIFICATION-A3: added coverage for the comma-plus-decimal case that
    # plain int() raised on before this change.
    @pytest.mark.parametrize("raw,expected", [
        ("1250.99",  1251),
        ("-1,250.9", -1251),
        ("1,250.4",  1250),
        ("1,250.5",  1250),   # round() is banker's rounding: .5 goes to even
    ])
    def test_decimal_rounds_instead_of_raising(self, raw, expected):
        # int("1250.50") raises ValueError, so _safe_int goes via float(), and
        # rounds rather than truncates so the saved value matches the rounded
        # figure the template renders with '{:,.0f}'
        assert app._safe_int(raw, 0) == expected
