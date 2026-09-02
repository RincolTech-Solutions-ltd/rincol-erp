"""Notification helpers — Telegram + Email (Gmail SMTP)."""
import os
import base64
import smtplib
import threading
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Config ────────────────────────────────────────────────────────────────────
_TG_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID", "")
_GMAIL_USER  = os.environ.get("GMAIL_SMTP_USER", "")
_GMAIL_PASS  = os.environ.get("GMAIL_SMTP_APP_PASSWORD", "")
_NOTIFY_TO   = [e.strip() for e in os.environ.get("NOTIFY_EMAILS", "").split(",") if e.strip()]
_APP_URL     = os.environ.get("APP_BASE_URL", "https://rincol-erp.onrender.com")

# Personal Telegram chat IDs — for DMs to assigned team members
_PERSONAL_IDS = {
    "hillary": os.environ.get("TELEGRAM_HILLARY_ID", ""),
    "dennis":  os.environ.get("TELEGRAM_DENNIS_ID", ""),
}


# ── Low-level senders ─────────────────────────────────────────────────────────

def _send_telegram(text: str, keyboard=None):
    """Send to the group channel. keyboard = inline_keyboard list (optional)."""
    if not _TG_TOKEN or not _TG_CHAT:
        return
    payload = {"chat_id": _TG_CHAT, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json=payload,
            timeout=8,
        )
    except Exception:
        pass


def _dm(person: str, text: str, keyboard=None):
    """Send a direct Telegram message to a team member by name (case-insensitive)."""
    chat_id = _PERSONAL_IDS.get((person or "").strip().lower(), "")
    if not _TG_TOKEN or not chat_id:
        return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            json=payload,
            timeout=8,
        )
    except Exception:
        pass


def _smtp_send(to: list, subject: str, html_body: str, attachments: list = None) -> bool:
    """Send via Gmail SMTP. attachments = [{"filename": "x.pdf", "content": base64str}].
    Returns True only on a confirmed successful send."""
    if not _GMAIL_USER or not _GMAIL_PASS:
        print(f"[EMAIL] SKIP — GMAIL_SMTP_USER/APP_PASSWORD not set. Would have sent to {to}: {subject}", flush=True)
        return False
    msg = MIMEMultipart()
    msg["From"]    = f"Rincol Tech Solutions <{_GMAIL_USER}>"
    msg["To"]      = ", ".join(to)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    for a in (attachments or []):
        part = MIMEApplication(base64.b64decode(a["content"]), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=a["filename"])
        msg.attach(part)
    try:
        print(f"[EMAIL] Sending to {to}: {subject}", flush=True)
        # Port 465 (implicit TLS) is blocked outbound on the Hetzner box;
        # 587 (STARTTLS) is open. Confirmed via direct port test 2026-09-02.
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(_GMAIL_USER, _GMAIL_PASS)
            # sendmail returns a dict of {recipient: (code, msg)} for any
            # recipient that was REFUSED but didn't raise (raises only if
            # ALL recipients are refused) — a non-empty dict means a partial
            # failure that would otherwise look identical to full success.
            refused = smtp.sendmail(_GMAIL_USER, to, msg.as_string())
            if refused:
                print(f"[EMAIL] PARTIAL FAILURE — refused: {refused}", flush=True)
                return False
        print(f"[EMAIL] OK — delivered via Gmail SMTP for {to}", flush=True)
        return True
    except Exception as e:
        print(f"[EMAIL] EXCEPTION sending to {to}: {e}", flush=True)
        return False


def _send_email(subject: str, html_body: str):
    if not _GMAIL_USER or not _NOTIFY_TO:
        return
    _smtp_send(_NOTIFY_TO, subject, html_body)


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
    "Pending Parts": "⏳", "Resolved": "✅", "Cancelled": "❌",
}
_QUOT_EMOJI = {
    "Draft": "📝", "Pending": "🕐", "Approved": "👍", "In Progress": "🔧",
    "Completed": "✅", "Cancelled": "❌",
}
_TASK_PRIORITY_EMOJI = {"Urgent": "🚨", "High": "🔴", "Normal": "🟡", "Low": "⚪"}


# ── Inline keyboards for DM notifications ─────────────────────────────────────
# Built here (not imported from tg_bot) to avoid circular imports.

def _task_kbd(tid):
    return [
        [{"text": "✅ Done",    "callback_data": f"task:done:{tid}"},
         {"text": "🔄 Status", "callback_data": f"task:status:{tid}"}],
        [{"text": "📝 Note",   "callback_data": f"task:note:{tid}"},
         {"text": "🗑 Delete", "callback_data": f"task:delete:{tid}"}],
        [{"text": "🔗 Open",   "url": f"{_APP_URL}/tasks/{tid}"}],
    ]


def _quot_kbd(qid, status: str = "Pending"):
    _action_btn = {
        "Draft":       {"text": "👍 Approve",      "callback_data": f"quot:setstatus:{qid}:Approved"},
        "Pending":     {"text": "👍 Approve",      "callback_data": f"quot:setstatus:{qid}:Approved"},
        "Approved":    {"text": "▶ In Progress",  "callback_data": f"quot:setstatus:{qid}:In Progress"},
        "In Progress": {"text": "✅ Complete",     "callback_data": f"quot:setstatus:{qid}:Completed"},
    }
    row1 = []
    if status in _action_btn:
        row1.append(_action_btn[status])
    row1.append({"text": "🔄 Status", "callback_data": f"quot:status:{qid}"})
    return [
        row1,
        [{"text": "💰 Payment", "callback_data": f"quot:payment:{qid}"},
         {"text": "📝 Note",    "callback_data": f"quot:note:{qid}"}],
        [{"text": "🔗 Open",    "url": f"{_APP_URL}/quotations/{qid}"}],
    ]


def _maint_kbd(mid):
    return [
        [{"text": "🔧 In Progress", "callback_data": f"maint:setstatus:{mid}:In Progress"},
         {"text": "✅ Resolved",    "callback_data": f"maint:setstatus:{mid}:Resolved"}],
        [{"text": "🔄 Status",      "callback_data": f"maint:status:{mid}"},
         {"text": "📝 Note",        "callback_data": f"maint:note:{mid}"}],
        [{"text": "🔗 Open",        "url": f"{_APP_URL}/maintenance/{mid}"}],
    ]


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

    cancel_reason = (r.get("cancellation_reason") or "").strip()

    tg = (f"{emoji} *Maintenance {action.title()}*\n"
          f"*Client:* {client}  |  {phone}\n"
          f"*Status:* {status}\n"
          f"*Date:* {date_}\n"
          f"*Description:* {desc}")
    if cancel_reason:
        tg += f"\n⚠️ *Cancellation Reason:* {cancel_reason}"
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View record]({link})"

    rows = (_row("Client", client) + _row("Phone", phone) +
            _row("Status", status) + _row("Date", date_) +
            _row("Description", desc))
    if cancel_reason:
        rows += _row("Cancellation Reason", f"<span style='color:#f87171'>{cancel_reason}</span>")
    if notes:
        rows += _row("Notes", notes)

    executor = (r.get("executor_name") or "").strip()

    def _go():
        kbd = _maint_kbd(mid)
        _send_telegram(tg, keyboard=kbd)
        _send_email(f"[Rincol ERP] Maintenance {action}: {client} — {status}",
                    _email_wrap(emoji, f"Maintenance {action.title()}", rows, link))
        # DM the assigned executor if they're a known team member
        if executor:
            _dm(executor, tg, keyboard=kbd)
    threading.Thread(target=_go, daemon=True).start()


# ── Quotations ────────────────────────────────────────────────────────────────

def notify_quotation(record: dict, action: str = "created"):
    """action: 'created' | 'updated'.
    Always internal-only: group Telegram + team email + DM Hillary & Dennis.
    Never emails the customer — the calling route does that synchronously via
    send_quotation_to_customer() so the flash message reflects the real result.
    """
    q              = record
    qid            = q.get("id", "")
    qno            = q.get("quotation_no", "—")
    client         = q.get("customer_name", "—")
    phone          = q.get("customer_phone") or "—"
    status         = q.get("status", "—")
    amount         = q.get("total_amount") or 0
    emoji          = _QUOT_EMOJI.get(status, "📋")
    link           = f"{_APP_URL}/quotations/{qid}"

    tg = (f"{emoji} *Quotation {action.title()}*\n"
          f"*Ref:* {qno}\n"
          f"*Client:* {client}  |  {phone}\n"
          f"*Amount:* UGX {amount:,.0f}\n"
          f"*Status:* {status}\n"
          f"[View quotation]({link})")

    rows = (_row("Ref", qno) + _row("Client", client) +
            _row("Phone", phone) + _row("Amount", f"UGX {amount:,.0f}") +
            _row("Status", status))

    def _go():
        kbd = _quot_kbd(qid, status)
        _send_telegram(tg, keyboard=kbd)
        _send_email(f"[Rincol ERP] Quotation {action}: {qno} — {client}",
                    _email_wrap(emoji, f"Quotation {action.title()}", rows, link, "View Quotation"))
        _dm("hillary", tg, keyboard=kbd)
        _dm("dennis", tg, keyboard=kbd)
        # NOTE: the customer-facing email is sent synchronously by the route
        # itself (app.py), not here — that's what lets the flash message
        # reflect the ACTUAL send result instead of firing this in the
        # background and guessing. Do not re-add a customer send in this
        # thread; it would double-send.
    threading.Thread(target=_go, daemon=True).start()


def send_quotation_to_customer(qno: str, client: str, amount: float,
                                customer_email: str, pdf_bytes: bytes,
                                status: str = "Pending") -> bool:
    print(f"[QUOT-EMAIL] Preparing {qno} for {customer_email} (status={status}, pdf={len(pdf_bytes or b'')} bytes)", flush=True)
    if not _GMAIL_PASS:
        print(f"[QUOT-EMAIL] SKIP — no Gmail SMTP password configured", flush=True)
        return False
    if status == "Approved":
        subject    = f"Approved Quotation {qno} — Rincol Tech Solutions Ltd"
        intro_line = (f"Thank you for approving quotation <strong>{qno}</strong>. "
                      f"Please find your confirmed quotation attached for your records.")
    else:
        subject    = f"Quotation {qno} — Rincol Tech Solutions Ltd"
        intro_line = (f"Thank you for your interest. Please find attached our quotation "
                      f"<strong>{qno}</strong> for your review.")

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
      <div style="background:#1a1d2e;padding:24px 28px;border-radius:8px 8px 0 0;text-align:center">
        <div style="color:#89b4fa;font-size:20px;font-weight:bold">Rincol Tech Solutions Ltd</div>
        <div style="color:#6b7280;font-size:12px;margin-top:4px">Solar & Energy Solutions</div>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:28px;border-radius:0 0 8px 8px">
        <p style="margin:0 0 16px">Dear <strong>{client}</strong>,</p>
        <p style="margin:0 0 16px;color:#374151">{intro_line}</p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:16px;margin:20px 0">
          <table style="border-collapse:collapse;width:100%">
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Quotation Ref</td><td><strong>{qno}</strong></td></tr>
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Total Amount</td><td><strong>UGX {amount:,.0f}</strong></td></tr>
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Status</td><td><strong>{status}</strong></td></tr>
          </table>
        </div>
        <p style="margin:0 0 16px;color:#374151">If you have any questions or would like to discuss further, please don't hesitate to reach out to us.</p>
        <p style="margin:0;color:#374151">
          Best regards,<br><strong>Rincol Tech Solutions Ltd</strong><br>
          <span style="color:#6b7280;font-size:12px">Tel: +256 775 102 684 | +256 701 586 001<br>Email: rincoltech@gmail.com<br>www.rincoltech.com</span>
        </p>
      </div>
    </div>"""

    return _smtp_send([customer_email], subject, html_body,
             attachments=[{"filename": f"{qno}.pdf",
                           "content": base64.b64encode(pdf_bytes).decode()}])


def notify_quotation_status(record: dict, new_status: str):
    """Dedicated notification for status-only changes.
    Always fires group Telegram + team email + DMs to Hillary & Dennis
    (internal-only, fire-and-forget). Does NOT email the customer — the
    calling route sends that synchronously via send_quotation_to_customer()
    so the user-facing flash message reflects the real outcome.
    """
    q              = record
    qid            = q.get("id", "")
    qno            = q.get("quotation_no", "—")
    client         = q.get("customer_name", "—")
    amount         = q.get("total_amount") or 0
    emoji          = _QUOT_EMOJI.get(new_status, "📋")
    link           = f"{_APP_URL}/quotations/{qid}"

    tg = (f"{emoji} *Quotation Status → {new_status}*\n"
          f"*Ref:* {qno}  |  {client}\n"
          f"*Amount:* UGX {amount:,.0f}\n"
          f"[View quotation]({link})")

    rows = (_row("Ref", qno) + _row("Client", client) +
            _row("Amount", f"UGX {amount:,.0f}") + _row("New Status", new_status))

    def _go():
        kbd = _quot_kbd(qid, new_status)
        _send_telegram(tg, keyboard=kbd)
        _send_email(f"[Rincol ERP] {qno} → {new_status}",
                    _email_wrap(emoji, f"Quotation → {new_status}", rows, link, "View Quotation"))
        _dm("hillary", tg, keyboard=kbd)
        _dm("dennis", tg, keyboard=kbd)
        # Customer email is sent synchronously by the route (app.py) so the
        # flash message reflects the real result — not repeated here.
    threading.Thread(target=_go, daemon=True).start()


# ── Receipts ──────────────────────────────────────────────────────────────────

def notify_receipt(record: dict, pdf_bytes: bytes = None):
    r              = record
    rid            = r.get("id", "")
    rno            = r.get("receipt_no", "—")
    client         = r.get("customer_name", "—")
    phone          = r.get("customer_phone") or "—"
    paid           = r.get("amount_paid") or 0
    balance        = r.get("balance") or 0
    method         = r.get("payment_method") or "Cash"
    customer_email = (r.get("customer_email") or "").strip()
    link           = f"{_APP_URL}/receipts/{rid}"

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

    def _go():
        _send_telegram(tg)
        _send_email(f"[Rincol ERP] 💰 Payment — {client} — UGX {paid:,.0f}",
                    _email_wrap("💰", "Payment Received", rows, link, "View Receipt"))
        if pdf_bytes and customer_email:
            _send_receipt_to_customer(rno, client, paid, balance, method, customer_email, pdf_bytes)
    threading.Thread(target=_go, daemon=True).start()


def _send_receipt_to_customer(rno: str, client: str, paid: float, balance: float,
                               method: str, customer_email: str, pdf_bytes: bytes):
    if not _GMAIL_PASS:
        return
    bal_note = "Fully settled — thank you!" if balance <= 0 else f"UGX {balance:,.0f} outstanding"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
      <div style="background:#1a1d2e;padding:24px 28px;border-radius:8px 8px 0 0;text-align:center">
        <div style="color:#89b4fa;font-size:20px;font-weight:bold">Rincol Tech Solutions Ltd</div>
        <div style="color:#6b7280;font-size:12px;margin-top:4px">Solar & Energy Solutions</div>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:28px;border-radius:0 0 8px 8px">
        <p style="margin:0 0 16px">Dear <strong>{client}</strong>,</p>
        <p style="margin:0 0 16px;color:#374151">Thank you for your payment. Please find your official receipt attached.</p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:16px;margin:20px 0">
          <table style="border-collapse:collapse;width:100%">
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Receipt Ref</td><td><strong>{rno}</strong></td></tr>
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Amount Paid</td><td><strong>UGX {paid:,.0f}</strong></td></tr>
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Payment Method</td><td><strong>{method}</strong></td></tr>
            <tr><td style="color:#6b7280;padding:4px 16px 4px 0">Balance</td><td><strong>{bal_note}</strong></td></tr>
          </table>
        </div>
        <p style="margin:0 0 16px;color:#374151">If you have any questions regarding this receipt, please don't hesitate to reach out.</p>
        <p style="margin:0;color:#374151">
          Best regards,<br><strong>Rincol Tech Solutions Ltd</strong><br>
          <span style="color:#6b7280;font-size:12px">Tel: +256 775 102 684 | +256 701 586 001<br>Email: rincoltech@gmail.com<br>www.rincoltech.com</span>
        </p>
      </div>
    </div>"""

    _smtp_send([customer_email], f"Payment Receipt {rno} — Rincol Tech Solutions Ltd", html_body,
             attachments=[{"filename": f"{rno}.pdf",
                           "content": base64.b64encode(pdf_bytes).decode()}])


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

    def _go():
        kbd = _task_kbd(tid)
        _send_telegram(tg, keyboard=kbd)
        _send_email(f"[Rincol ERP] Task {action}: {title}",
                    _email_wrap(emoji, f"Task {action.title()}", rows, link, "View Task"))
        # DM the assigned person(s) directly with action buttons
        if assigned and assigned.lower() not in ("unassigned", ""):
            if assigned.lower() == "both":
                _dm("hillary", tg, keyboard=kbd)
                _dm("dennis",  tg, keyboard=kbd)
            else:
                _dm(assigned, tg, keyboard=kbd)
    threading.Thread(target=_go, daemon=True).start()


# ── Customer statement ────────────────────────────────────────────────────────

def send_customer_statement(customer: dict, stats: dict, pdf_bytes: bytes, statement_url: str):
    """Email a customer their account statement PDF + link to the live statement page."""
    if not _GMAIL_PASS or not customer.get("email"):
        return
    name    = customer.get("name", "Valued Customer")
    cust_no = customer.get("customer_no", "")
    total_o = stats.get("total_outstanding", 0) or 0
    owed_line = (f"UGX {total_o:,.0f} outstanding across your account."
                 if total_o > 0 else "Your account is fully settled — thank you!")

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
      <div style="background:#1a1d2e;padding:24px 28px;border-radius:8px 8px 0 0;text-align:center">
        <div style="color:#89b4fa;font-size:20px;font-weight:bold">Rincol Tech Solutions Ltd</div>
        <div style="color:#6b7280;font-size:12px;margin-top:4px">Solar & Energy Solutions</div>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:28px;border-radius:0 0 8px 8px">
        <p style="margin:0 0 16px">Dear <strong>{name}</strong>,</p>
        <p style="margin:0 0 16px;color:#374151">
          Please find attached your account statement (Ref: <strong>{cust_no}</strong>).
          {owed_line}
        </p>
        <p style="margin:0 0 16px;color:#374151">
          You can also view your live statement online at any time using the link below:
        </p>
        <div style="margin:20px 0;text-align:center">
          <a href="{statement_url}"
             style="background:#89b4fa;color:#1a1d2e;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">
            View Statement Online
          </a>
        </div>
        <p style="margin:0 0 16px;color:#374151">
          If you have any questions, please don't hesitate to reach out.
        </p>
        <p style="margin:0;color:#374151">
          Best regards,<br><strong>Rincol Tech Solutions Ltd</strong><br>
          <span style="color:#6b7280;font-size:12px">
            Tel: +256 775 102 684 | +256 701 586 001<br>
            Email: rincoltech@gmail.com | www.rincoltech.com
          </span>
        </p>
      </div>
    </div>"""

    _smtp_send([customer["email"]],
             f"Account Statement — {name} ({cust_no}) — Rincol Tech Solutions",
             html_body,
             attachments=[{"filename": f"Statement_{cust_no}.pdf",
                           "content": base64.b64encode(pdf_bytes).decode()}])


# ── Balancing jobs ───────────────────────────────────────────────────────────

def notify_balancing_job(record: dict, action: str = "created"):
    """action: 'created' | 'updated'"""
    j        = record
    jid      = j.get("id", "")
    job_name = j.get("job_name") or "—"
    qno      = j.get("quotation_no") or "—"
    quoted   = j.get("quoted") or 0
    h_ratio  = j.get("h_ratio") or 0
    d_ratio  = j.get("d_ratio") or 0
    notes    = (j.get("notes") or "").strip()
    link     = f"{_APP_URL}/balancing/{jid}"
    emoji    = "📊"

    tg = (f"{emoji} *Balancing Job {action.title()}*\n"
          f"*Job:* {job_name}\n"
          f"*Quotation:* {qno}\n"
          f"*Quoted:* UGX {quoted:,.0f}\n"
          f"*Split:* Hillary {h_ratio}% / Dennis {d_ratio}%")
    if notes:
        tg += f"\n*Notes:* {notes}"
    tg += f"\n[View job]({link})"

    rows = (_row("Job", job_name) + _row("Quotation", qno) +
            _row("Quoted Amount", f"UGX {quoted:,.0f}") +
            _row("Split", f"Hillary {h_ratio}% / Dennis {d_ratio}%"))
    if notes:
        rows += _row("Notes", notes)

    _fire(tg,
          f"[Rincol ERP] Balancing {action}: {job_name}",
          _email_wrap(emoji, f"Balancing Job {action.title()}", rows, link, "View Job"))


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

    def _go():
        _send_telegram(tg)
        _send_email(f"[Rincol ERP] 🤝 Settlement — {from_person} → {to_person} — UGX {amount:,.0f}",
                    _email_wrap("🤝", "Settlement Recorded", rows, link, "View Balancing"))
        # DM both parties
        _dm(from_person, tg)
        _dm(to_person, tg)
    threading.Thread(target=_go, daemon=True).start()
