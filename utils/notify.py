"""Notification helpers — Telegram + Gmail."""
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Config (loaded from environment) ─────────────────────────────────────────
_TG_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
_GM_USER   = os.environ.get("GMAIL_USER", "")
_GM_PASS   = os.environ.get("GMAIL_APP_PASSWORD", "")
_NOTIFY_TO = [e.strip() for e in os.environ.get("NOTIFY_EMAILS", "").split(",") if e.strip()]
_APP_URL   = os.environ.get("APP_BASE_URL", "https://rincol-erp.onrender.com")


# ── Internal send helpers ─────────────────────────────────────────────────────

def _send_telegram(text: str):
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json={"chat_id": _TG_CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=8,
        )
    except Exception:
        pass


def _send_email(subject: str, html_body: str):
    if not _GM_USER or not _GM_PASS or not _NOTIFY_TO:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rincol ERP <{_GM_USER}>"
        msg["To"]      = ", ".join(_NOTIFY_TO)
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(_GM_USER, _GM_PASS)
            s.sendmail(_GM_USER, _NOTIFY_TO, msg.as_string())
    except Exception:
        pass


def _fire(tg_text: str, email_subject: str, email_html: str):
    """Send both notifications in a background thread so the HTTP response isn't delayed."""
    def _go():
        _send_telegram(tg_text)
        _send_email(email_subject, email_html)
    threading.Thread(target=_go, daemon=True).start()


# ── Status emoji map ──────────────────────────────────────────────────────────
_STATUS_EMOJI = {
    "Scheduled":    "📅",
    "Open":         "🔓",
    "In Progress":  "🔧",
    "Pending Parts":"⏳",
    "Resolved":     "✅",
}


# ── Public notification functions ─────────────────────────────────────────────

def notify_maintenance(record: dict, action: str = "updated"):
    """
    Send a Telegram + email notification for a maintenance record change.
    action: "created" | "updated"
    """
    r      = record
    mid    = r.get("id", "")
    client = r.get("client_name", "—")
    phone  = r.get("client_phone") or "—"
    status = r.get("status", "—")
    emoji  = _STATUS_EMOJI.get(status, "🔔")
    date_  = r.get("visit_date") or "—"
    desc   = (r.get("problem") or "—").strip()
    notes  = (r.get("notes") or "").strip()
    link   = f"{_APP_URL}/maintenance/{mid}"

    # ── Telegram (Markdown) ──────────────────────────────────────────────────
    tg = (
        f"{emoji} *Maintenance {action.title()}*\n"
        f"*Client:* {client}  |  {phone}\n"
        f"*Status:* {status}\n"
        f"*Date:* {date_}\n"
        f"*Description:* {desc}"
    )
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View record]({link})"

    # ── Email (HTML) ─────────────────────────────────────────────────────────
    subject = f"[Rincol ERP] Maintenance {action}: {client} — {status}"

    def row(label, value):
        return f"<tr><td style='color:#6b7280;padding:4px 12px 4px 0;white-space:nowrap'>{label}</td><td style='padding:4px 0'><strong>{value}</strong></td></tr>"

    rows = "".join([
        row("Client",      client),
        row("Phone",       phone),
        row("Status",      status),
        row("Date",        date_),
        row("Description", desc),
    ])
    if notes:
        rows += row("Notes", notes)

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">
      <div style="background:#1a1d2e;color:#89b4fa;padding:16px 20px;border-radius:8px 8px 0 0">
        <strong style="font-size:16px">{emoji} Maintenance {action.title()}</strong>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px">
        <table style="border-collapse:collapse;width:100%">{rows}</table>
        <div style="margin-top:16px">
          <a href="{link}" style="background:#89b4fa;color:#1a1d2e;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold">
            View Record
          </a>
        </div>
      </div>
      <p style="color:#9ca3af;font-size:11px;margin-top:12px">Rincol ERP · {_APP_URL}</p>
    </div>"""

    _fire(tg, subject, html)
