"""
Tests for WhatsApp recipient phone normalization.

This function decides who receives a customer's quotation PDF. The bridge does
not verify that a number is on WhatsApp before sending and reports success
regardless, so a wrong-but-plausible result here delivers customer documents to
a stranger. The refusal cases below matter as much as the accepted ones.

Regression origin: QT-2026-052 failed to send to a US customer (+18578698733)
because the original implementation only understood Ugandan formats.
"""
import pytest

from utils.whatsapp import _normalize_phone


@pytest.mark.parametrize("raw,expected", [
    # International, explicit +
    ("+18578698733",       "18578698733"),    # the number that failed (US)
    ("+1 (857) 869-8733",  "18578698733"),    # as WhatsApp displays it
    ("+256768657364",      "256768657364"),
    ("+256 775 102 684",   "256775102684"),

    # Ugandan local forms
    ("0775636111",         "256775636111"),
    ("0782576807",         "256782576807"),
    ("779289683",          "256779289683"),   # bare 9-digit
    ("256775636111",       "256775636111"),

    # Malformed but recoverable: a "+" does not mean the digits are clean
    ("2560775636111",      "256775636111"),   # double country prefix
    ("+0775102684",        "256775102684"),   # + on a local number
    ("+256 0775 102 684",  "256775102684"),   # + and double prefix

    # "00" international access prefix
    ("00256775102684",     "256775102684"),
    ("0018578698733",      "18578698733"),
])
def test_accepts(raw, expected):
    assert _normalize_phone(raw) == expected


@pytest.mark.parametrize("raw,why", [
    ("",                 "empty"),
    (None,               "none"),
    ("n/a",              "no digits at all"),
    ("123",              "far too short"),
    ("6465551234",       "bare 10-digit US national: would misparse as +64 (NZ)"),
    ("4695551234",       "bare 10-digit US national: would misparse as +46 (SE)"),
    ("0256775102684",    "single leading zero before a country code"),
    ("07751026840",      "11-digit typo, leading zero"),
    ("07911123456",      "UK local form, no country code"),
    ("25677510268412",   "256 with an extension glued on"),
    ("+256-775-102-684 ext 12", "same, with a + and an explicit extension"),
])
def test_refuses(raw, why):
    assert _normalize_phone(raw) is None, why
