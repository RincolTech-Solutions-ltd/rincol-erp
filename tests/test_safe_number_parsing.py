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
