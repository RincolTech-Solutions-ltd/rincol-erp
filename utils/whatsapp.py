"""Send documents to customers over WhatsApp via the shared Hetzner bridge.

The bridge (whatsapp-bridge.service, port 8080 on this same box) is Hillary's
personal WhatsApp number — Rincol has no dedicated WhatsApp Business number,
so customer-facing sends go out from that account, same as before the
Render→Hetzner migration.
"""
import os
import re
import tempfile

import requests

_WA_BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8080")


def _normalize_phone(phone: str):
    """Normalize a phone number to international digits (no +), the format the
    WhatsApp bridge expects for a phone-number recipient. Returns None when the
    number can't be resolved safely.

    The bridge does NOT check whether a number is on WhatsApp before sending,
    and reports success either way, so a wrong-but-plausible number here means
    a customer's quotation silently goes to a stranger. Rules, in order:

    1. "00" is the international access prefix, so 00256... is treated as +256...
    2. Ugandan local forms are expanded even when a "+" was also typed, because
       a "+" does not guarantee well-formed digits: 0XXXXXXXXX (10) and the
       double-prefixed 2560XXXXXXXXX (13) both collapse to 256XXXXXXXXX, and a
       bare 9-digit number gets the 256 country code.
    3. Anything claiming country code 256 must be exactly 12 digits. A longer
       one is a typo or has an extension glued on, and is refused.
    4. A leading 0 can never survive into E.164, so it is refused.
    5. With an explicit "+" (or a resolved 00), any 8..15 digits pass.
    6. Without one, assume the country code is already present (e.g.
       18578698733) but require 11..15 digits, so a bare 10-digit national
       number is refused rather than misread as another country's code.
    """
    if not phone:
        return None
    raw = phone.strip()
    had_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    if digits.startswith("00"):
        digits, had_plus = digits[2:], True

    if digits.startswith("0") and len(digits) == 10:
        digits, had_plus = "256" + digits[1:], True
    elif digits.startswith("2560") and len(digits) == 13:
        digits, had_plus = "256" + digits[4:], True
    elif len(digits) == 9:
        digits, had_plus = "256" + digits, True

    if digits.startswith("256") and len(digits) != 12:
        return None
    if digits.startswith("0"):
        return None

    if had_plus:
        return digits if 8 <= len(digits) <= 15 else None
    return digits if 11 <= len(digits) <= 15 else None


def send_quotation_whatsapp(phone: str, quotation_no: str, pdf_bytes: bytes, caption: str):
    """Send the quotation PDF with a caption to a customer's WhatsApp.
    Returns (success: bool, message: str)."""
    number = _normalize_phone(phone)
    if not number:
        return False, f"no usable WhatsApp number from '{phone}'"

    # quotation_no reaches here from a user-editable form field — sanitize
    # before using it as a filename so it can't escape the temp dir or
    # collide with an unintended path (the bridge, running as root, reads
    # whatever path we hand it).
    safe_no = re.sub(r"[^A-Za-z0-9._-]", "_", quotation_no) or "quotation"
    tmpdir = tempfile.mkdtemp(prefix="rincol-wa-")
    path = os.path.join(tmpdir, f"{safe_no}.pdf")
    try:
        with open(path, "wb") as f:
            f.write(pdf_bytes)
        r = requests.post(f"{_WA_BRIDGE_URL}/api/send", json={
            "recipient": number,
            "message": caption,
            "media_path": path,
        }, timeout=60)
        data = r.json()
        success = bool(data.get("success"))
        message = data.get("message", "")
        print(f"[WHATSAPP] {'OK' if success else 'FAILED'} to {number} ({quotation_no}): {message}", flush=True)
        return success, message
    except requests.exceptions.Timeout:
        print(f"[WHATSAPP] TIMEOUT sending to {number} ({quotation_no}) — may still deliver", flush=True)
        return False, "bridge did not respond in time — check WhatsApp before resending, it may still arrive"
    except Exception as e:
        print(f"[WHATSAPP] EXCEPTION sending to {number} ({quotation_no}): {e}", flush=True)
        return False, str(e)
    finally:
        try:
            os.remove(path)
            os.rmdir(tmpdir)
        except OSError:
            pass
