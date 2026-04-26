"""Notification helpers — Telegram + Gmail."""
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Config ────────────────────────────────────────────────────────────────────
_TG_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
_GM_USER   = os.environ.get("GMAIL_USER", "")
_GM_PASS   = os.environ.get("GMAIL_APP_PASSWORD", "")
_NOTIFY_TO = [e.strip() for e in os.environ.get("NOTIFY_EMAILS", "").split(",") if e.strip()]
_APP_URL   = os.environ.get("APP_BASE_URL", "https://rincol-erp.onrender.com")


# ── Low-level senders ─────────────────────────────────────────────────────────

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


def _fire(tg_text: str, subject: str, html: str):
    """Fire both channels in a background thread — no delay to HTTP response."""
    def _go():
        _send_telegram(tg_text)
        _send_email(subject, html)
    threading.Thread(target=_go, daemon=True).start()


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _row(label, value):
    return (f"<tr>"
            f"<td style='color:#6b7280;padding:4px 12px 4px 0;white-space:nowrap'>{label}</td>"
            f"<td style='padding:4px 0'><strong>{value}</strong></td>"
            f"</tr>")


def _email_wrap(header_emoji: str, header_text: str, rows_html: str, link: str, link_label: str = "View Record") -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto">
      <div style="background:#1a1d2e;color:#89b4fa;padding:16px 20px;border-radius:8px 8px 0 0">
        <strong style="font-size:16px">{header_emoji} {header_text}</strong>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px">
        <table style="border-collapse:collapse;width:100%">{rows_html}</table>
        <div style="margin-top:16px">
          <a href="{link}" style="background:#89b4fa;color:#1a1d2e;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold">
            {link_label}
          </a>
        </div>
      </div>
      <p style="color:#9ca3af;font-size:11px;margin-top:12px">Rincol ERP · {_APP_URL}</p>
    </div>"""


# ── Status emojis ─────────────────────────────────────────────────────────────

_MAINT_EMOJI = {
    "Scheduled": "📅", "Open": "🔓", "In Progress": "🔧",
    "Pending Parts": "⏳", "Resolved": "✅",
}
_QUOT_EMOJI = {
    "Pending": "🕐", "Approved": "👍", "In Progress": "🔧",
    "Completed": "✅", "Cancelled": "❌",
}
_TASK_PRIORITY_EMOJI = {"Urgent": "🚨", "High": "🔴", "Normal": "🟡", "Low": "⚪"}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC NOTIFY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

# ── Maintenance ───────────────────────────────────────────────────────────────

def notify_maintenance(record: dict, action: str = "updated"):
    r      = record
    mid    = r.get("id", "")
    client = r.get("client_name", "—")
    phone  = r.get("client_phone") or "—"
    status = r.get("status", "—")
    emoji  = _MAINT_EMOJI.get(status, "🔔")
    date_  = r.get("visit_date") or "—"
    desc   = (r.get("problem") or "—").strip()
    notes  = (r.get("notes") or "").strip()
    link   = f"{_APP_URL}/maintenance/{mid}"

    tg = (f"{emoji} *Maintenance {action.title()}*\n"
          f"*Client:* {client}  |  {phone}\n"
          f"*Status:* {status}\n"
          f"*Date:* {date_}\n"
          f"*Description:* {desc}")
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View record]({link})"

    rows = (_row("Client", client) + _row("Phone", phone) +
            _row("Status", status) + _row("Date", date_) +
            _row("Description", desc))
    if notes:
        rows += _row("Notes", notes)

    _fire(tg,
          f"[Rincol ERP] Maintenance {action}: {client} — {status}",
          _email_wrap(emoji, f"Maintenance {action.title()}", rows, link))


# ── Quotations ────────────────────────────────────────────────────────────────

def notify_quotation(record: dict, action: str = "created"):
    """action: 'created' | 'updated'"""
    q      = record
    qid    = q.get("id", "")
    qno    = q.get("quotation_no", "—")
    client = q.get("customer_name", "—")
    phone  = q.get("customer_phone") or "—"
    status = q.get("status", "—")
    amount = q.get("total_amount") or 0
    emoji  = _QUOT_EMOJI.get(status, "📋")
    link   = f"{_APP_URL}/quotations/{qid}"

    tg = (f"{emoji} *Quotation {action.title()}*\n"
          f"*Ref:* {qno}\n"
          f"*Client:* {client}  |  {phone}\n"
          f"*Amount:* UGX {amount:,.0f}\n"
          f"*Status:* {status}\n"
          f"[View quotation]({link})")

    rows = (_row("Ref", qno) + _row("Client", client) +
            _row("Phone", phone) + _row("Amount", f"UGX {amount:,.0f}") +
            _row("Status", status))

    _fire(tg,
          f"[Rincol ERP] Quotation {action}: {qno} — {client}",
          _email_wrap(emoji, f"Quotation {action.title()}", rows, link, "View Quotation"))


def notify_quotation_status(record: dict, new_status: str):
    """Dedicated notification for status-only changes."""
    q      = record
    qid    = q.get("id", "")
    qno    = q.get("quotation_no", "—")
    client = q.get("customer_name", "—")
    amount = q.get("total_amount") or 0
    emoji  = _QUOT_EMOJI.get(new_status, "📋")
    link   = f"{_APP_URL}/quotations/{qid}"

    tg = (f"{emoji} *Quotation Status → {new_status}*\n"
          f"*Ref:* {qno}  |  {client}\n"
          f"*Amount:* UGX {amount:,.0f}\n"
          f"[View quotation]({link})")

    rows = (_row("Ref", qno) + _row("Client", client) +
            _row("Amount", f"UGX {amount:,.0f}") + _row("New Status", new_status))

    _fire(tg,
          f"[Rincol ERP] {qno} → {new_status}",
          _email_wrap(emoji, f"Quotation → {new_status}", rows, link, "View Quotation"))


# ── Receipts ──────────────────────────────────────────────────────────────────

def notify_receipt(record: dict):
    r       = record
    rid     = r.get("id", "")
    rno     = r.get("receipt_no", "—")
    client  = r.get("customer_name", "—")
    phone   = r.get("customer_phone") or "—"
    paid    = r.get("amount_paid") or 0
    balance = r.get("balance") or 0
    method  = r.get("payment_method") or "Cash"
    link    = f"{_APP_URL}/receipts/{rid}"

    bal_note = "SETTLED ✅" if balance <= 0 else f"UGX {balance:,.0f} still owed"

    tg = (f"💰 *Payment Received*\n"
          f"*Receipt:* {rno}\n"
          f"*Client:* {client}  |  {phone}\n"
          f"*Amount Paid:* UGX {paid:,.0f}\n"
          f"*Balance:* {bal_note}\n"
          f"*Method:* {method}\n"
          f"[View receipt]({link})")

    rows = (_row("Receipt", rno) + _row("Client", client) +
            _row("Phone", phone) + _row("Amount Paid", f"UGX {paid:,.0f}") +
            _row("Balance", bal_note) + _row("Method", method))

    _fire(tg,
          f"[Rincol ERP] 💰 Payment — {client} — UGX {paid:,.0f}",
          _email_wrap("💰", "Payment Received", rows, link, "View Receipt"))


# ── Tasks ─────────────────────────────────────────────────────────────────────

def notify_task(record: dict, action: str = "created"):
    """action: 'created' | 'updated' | 'completed'"""
    t        = record
    tid      = t.get("id", "")
    title    = t.get("title", "—")
    assigned = t.get("assigned_to") or "Unassigned"
    priority = t.get("priority") or "Normal"
    status   = t.get("status") or "Pending"
    due      = t.get("due_date") or "—"
    notes    = (t.get("notes") or "").strip()
    p_emoji  = _TASK_PRIORITY_EMOJI.get(priority, "🟡")
    emoji    = "✅" if action == "completed" else p_emoji
    link     = f"{_APP_URL}/tasks/{tid}"

    tg = (f"{emoji} *Task {action.title()}*\n"
          f"*{title}*\n"
          f"*Assigned:* {assigned}\n"
          f"*Priority:* {priority}  |  *Status:* {status}\n"
          f"*Due:* {due}")
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View task]({link})"

    rows = (_row("Title", title) + _row("Assigned To", assigned) +
            _row("Priority", priority) + _row("Status", status) +
            _row("Due Date", due))
    if notes:
        rows += _row("Notes", notes)

    _fire(tg,
          f"[Rincol ERP] Task {action}: {title}",
          _email_wrap(emoji, f"Task {action.title()}", rows, link, "View Task"))


# ── Balancing settlements ─────────────────────────────────────────────────────

def notify_settlement(job: dict, amount: float, from_person: str, to_person: str, notes: str = ""):
    """Fired when a settlement payment is recorded in a balancing job."""
    jid      = job.get("id", "")
    job_name = job.get("job_name") or job.get("quotation_no") or "—"
    link     = f"{_APP_URL}/balancing/{jid}"

    tg = (f"🤝 *Settlement Recorded*\n"
          f"*Job:* {job_name}\n"
          f"*From:* {from_person}  →  *To:* {to_person}\n"
          f"*Amount:* UGX {amount:,.0f}")
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View balancing]({link})"

    rows = (_row("Job", job_name) + _row("From", from_person) +
            _row("To", to_person) + _row("Amount", f"UGX {amount:,.0f}"))
    if notes:
        rows += _row("Notes", notes)

    _fire(tg,
          f"[Rincol ERP] 🤝 Settlement — {from_person} → {to_person} — UGX {amount:,.0f}",
          _email_wrap("🤝", "Settlement Recorded", rows, link, "View Balancing"))
