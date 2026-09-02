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


def _normalize_ug_phone(phone: str):
    """Normalize a Ugandan phone number to international digits (256XXXXXXXXX,
    no +), the format the WhatsApp bridge expects for a phone-number recipient.
    Returns None if it doesn't look like a usable number."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0") and len(digits) == 10:
        return "256" + digits[1:]
    if digits.startswith("2560") and len(digits) == 13:
        return "256" + digits[4:]
    if digits.startswith("256") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return "256" + digits
    return None


def send_quotation_whatsapp(phone: str, quotation_no: str, pdf_bytes: bytes, caption: str):
    """Send the quotation PDF with a caption to a customer's WhatsApp.
    Returns (success: bool, message: str)."""
    number = _normalize_ug_phone(phone)
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
