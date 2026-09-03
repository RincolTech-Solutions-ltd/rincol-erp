"""Telegram bot — two-way interaction with Rincol ERP.

Callback data format (Telegram max 64 bytes):
  {type}:{action}:{id}           — action with no extra value
  {type}:{action}:{id}:{value}   — action with a value (status, method, etc.)

  Types : task | quot | maint | rcpt | bal | paymethod | register
  Actions documented per section below.
"""
import json
import os
from datetime import date

import requests

from utils.db import execute, query, query_one

# ── Config ─────────────────────────────────────────────────────────────────────
_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_APP_URL = os.environ.get("APP_BASE_URL", "https://rincol-erp.onrender.com")
_API     = f"https://api.telegram.org/bot{_TOKEN}"

# ── Status lists ───────────────────────────────────────────────────────────────
_TASK_STATUSES  = ["Pending", "In Progress", "Done"]
_QUOT_STATUSES  = ["Draft", "Pending", "Approved", "In Progress", "Completed", "Cancelled"]
_MAINT_STATUSES = ["Open", "In Progress", "Resolved", "Pending Parts", "Cancelled"]
_PRIORITY_EMOJI = {"Urgent": "🚨", "High": "🔴", "Normal": "🟡", "Low": "⚪"}
_QUOT_EMOJI     = {"Draft": "📝", "Pending": "🕐", "Approved": "👍",
                   "In Progress": "🔧", "Completed": "✅", "Cancelled": "❌"}
_MAINT_EMOJI    = {"Open": "🔓", "In Progress": "🔧", "Resolved": "✅",
                   "Pending Parts": "⏳", "Cancelled": "❌"}


# ══════════════════════════════════════════════════════════════════════════════
# Telegram API helpers
# ══════════════════════════════════════════════════════════════════════════════

def _post(method: str, payload: dict) -> dict:
    if not _TOKEN:
        return {}
    try:
        r = requests.post(f"{_API}/{method}", json=payload, timeout=10)
        return r.json()
    except Exception:
        return {}


def send(chat_id, text: str, keyboard=None, parse_mode="Markdown") -> dict:
    """Send a plain message, optionally with an inline keyboard."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _post("sendMessage", payload)


def force_reply(chat_id, prompt: str):
    """Prompt for text input — user's next message is treated as the reply."""
    return _post("sendMessage", {
        "chat_id": chat_id,
        "text": prompt,
        "parse_mode": "Markdown",
        "reply_markup": {"force_reply": True, "selective": True},
    })


def answer_cb(callback_query_id, text="", alert=False):
    _post("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": alert,
    })


def edit_msg(chat_id, message_id, text: str, keyboard=None):
    payload = {"chat_id": chat_id, "message_id": message_id,
               "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    _post("editMessageText", payload)


# ══════════════════════════════════════════════════════════════════════════════
# Session helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_session(chat_id):
    return query_one(
        "SELECT * FROM telegram_sessions WHERE chat_id=%s", (str(chat_id),))


def save_session(chat_id, context, record_type="", record_id="", step="", data=None):
    data_str = json.dumps(data or {})
    if get_session(chat_id):
        execute("""UPDATE telegram_sessions
                   SET context=%s, record_type=%s, record_id=%s,
                       step=%s, data=%s, updated_at=NOW()
                   WHERE chat_id=%s""",
                (context, record_type, str(record_id), step, data_str, str(chat_id)))
    else:
        execute("""INSERT INTO telegram_sessions
                   (chat_id, context, record_type, record_id, step, data)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (str(chat_id), context, record_type, str(record_id), step, data_str))


def clear_session(chat_id):
    execute("DELETE FROM telegram_sessions WHERE chat_id=%s", (str(chat_id),))


def _session_data(sess) -> dict:
    try:
        return json.loads(sess.get("data") or "{}")
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# User helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_person(chat_id) -> str | None:
    """Return 'hillary' | 'dennis' | None if unregistered."""
    row = query_one(
        "SELECT person_name FROM telegram_users WHERE chat_id=%s", (str(chat_id),))
    return row["person_name"].lower() if row else None


def _register_user(chat_id, username, person_name):
    if get_person(chat_id):
        execute("UPDATE telegram_users SET username=%s, person_name=%s WHERE chat_id=%s",
                (username, person_name.lower(), str(chat_id)))
    else:
        execute("INSERT INTO telegram_users (chat_id, username, person_name) VALUES (%s,%s,%s)",
                (str(chat_id), username, person_name.lower()))


# ══════════════════════════════════════════════════════════════════════════════
# Keyboard builders  (also exported for use by notify.py)
# ══════════════════════════════════════════════════════════════════════════════

def task_keyboard(tid):
    return [
        [{"text": "✅ Done",    "callback_data": f"task:done:{tid}"},
         {"text": "🔄 Status", "callback_data": f"task:status:{tid}"}],
        [{"text": "📝 Note",   "callback_data": f"task:note:{tid}"},
         {"text": "🗑 Delete", "callback_data": f"task:delete:{tid}"}],
        [{"text": "🔗 Open",   "url": f"{_APP_URL}/tasks/{tid}"}],
    ]


def quot_keyboard(qid):
    return [
        [{"text": "👍 Approve", "callback_data": f"quot:setstatus:{qid}:Approved"},
         {"text": "🔄 Status", "callback_data": f"quot:status:{qid}"}],
        [{"text": "💰 Payment", "callback_data": f"quot:payment:{qid}"},
         {"text": "📝 Note",    "callback_data": f"quot:note:{qid}"}],
        [{"text": "🔗 Open",    "url": f"{_APP_URL}/quotations/{qid}"}],
    ]


def maint_keyboard(mid):
    return [
        [{"text": "🔧 In Progress", "callback_data": f"maint:setstatus:{mid}:In Progress"},
         {"text": "✅ Resolved",    "callback_data": f"maint:setstatus:{mid}:Resolved"}],
        [{"text": "🔄 Status",      "callback_data": f"maint:status:{mid}"},
         {"text": "📝 Note",        "callback_data": f"maint:note:{mid}"}],
        [{"text": "🔗 Open",        "url": f"{_APP_URL}/maintenance/{mid}"}],
    ]


def _status_keyboard(rtype, rid, statuses):
    """Generic status-picker keyboard — 2 buttons per row."""
    rows, row = [], []
    for s in statuses:
        row.append({"text": s, "callback_data": f"{rtype}:setstatus:{rid}:{s}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "← Back", "callback_data": f"{rtype}:back:{rid}"}])
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Text formatters
# ══════════════════════════════════════════════════════════════════════════════

def _task_text(t) -> str:
    p = _PRIORITY_EMOJI.get(t.get("priority", "Normal"), "🟡")
    return (f"{p} *{t['title']}*\n"
            f"Assigned: {t.get('assigned_to') or '—'}  |  Due: {t.get('due_date') or '—'}\n"
            f"Status: {t.get('status', '—')}  |  Priority: {t.get('priority', '—')}")


def _quot_text(q) -> str:
    e = _QUOT_EMOJI.get(q.get("status", ""), "📋")
    return (f"{e} *{q.get('quotation_no', '—')}*\n"
            f"Client: {q.get('customer_name', '—')}\n"
            f"Amount: UGX {(q.get('total_amount') or 0):,.0f}\n"
            f"Status: {q.get('status', '—')}")


def _maint_text(m) -> str:
    e = _MAINT_EMOJI.get(m.get("status", ""), "🔔")
    return (f"{e} *Job #{m['id']} — {m.get('client_name', '—')}*\n"
            f"Date: {m.get('visit_date', '—')}  |  Status: {m.get('status', '—')}\n"
            f"Problem: {(m.get('problem') or '—')[:80]}")


# ══════════════════════════════════════════════════════════════════════════════
# Main dispatcher
# ══════════════════════════════════════════════════════════════════════════════

def handle_update(update: dict):
    """Entry point called from the Flask webhook route."""
    try:
        if "callback_query" in update:
            _handle_callback(update["callback_query"])
        elif "message" in update:
            _handle_message(update["message"])
    except Exception as e:
        print(f"[tg_bot] unhandled error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Message handler
# ══════════════════════════════════════════════════════════════════════════════

def _handle_message(msg: dict):
    chat_id  = msg["chat"]["id"]
    text     = (msg.get("text") or "").strip()
    username = msg.get("from", {}).get("username", "")

    if text.lower().startswith("/start"):
        _cmd_start(chat_id, username)
        return

    person = get_person(chat_id)
    if not person:
        # Group chats aren't "registered" like a person — log the chat_id so
        # whoever added the bot to a group can find it and set it as
        # TELEGRAM_CHAT_ID, instead of it being a silent dead end.
        print(f"[TELEGRAM] Message from unregistered chat_id={chat_id} (type={msg['chat'].get('type')}, title={msg['chat'].get('title')})", flush=True)
        if msg["chat"].get("type") == "private":
            send(chat_id, "Please register first. Send /start")
        return

    # ForceReply response — user replied to one of our prompts
    sess = get_session(chat_id)
    if sess and msg.get("reply_to_message"):
        _handle_session_reply(chat_id, text, sess, person)
        return

    # Command routing
    cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""
    {
        "/help":        lambda: _cmd_help(chat_id),
        "/mytasks":     lambda: _cmd_mytasks(chat_id, person),
        "/tasks":       lambda: _cmd_tasks(chat_id),
        "/quotations":  lambda: _cmd_quotations(chat_id),
        "/maintenance": lambda: _cmd_maintenance(chat_id),
        "/receipts":    lambda: _cmd_receipts(chat_id),
        "/balancing":   lambda: _cmd_balancing(chat_id),
        "/newtask":     lambda: _cmd_newtask(chat_id),
        "/newjob":      lambda: _cmd_newjob(chat_id),
        "/newreceipt":  lambda: _cmd_newreceipt(chat_id),
        "/today":       lambda: _cmd_today(chat_id),
        "/summary":     lambda: _cmd_summary(chat_id),
    }.get(cmd, lambda: send(chat_id, "Unknown command. Send /help"))()


# ══════════════════════════════════════════════════════════════════════════════
# Callback handler
# ══════════════════════════════════════════════════════════════════════════════

def _handle_callback(cb: dict):
    cid     = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    msg_id  = cb["message"]["message_id"]
    data    = cb.get("data", "")
    from_u  = cb.get("from", {}).get("username", "")

    # Registration — before person check
    if data.startswith("register:"):
        _, name = data.split(":", 1)
        _register_user(chat_id, from_u, name)
        answer_cb(cid, f"Registered as {name.title()}!")
        edit_msg(chat_id, msg_id,
                 f"✅ Registered as *{name.title()}*.\n\nSend /help to see all commands.")
        return

    person = get_person(chat_id)
    if not person:
        answer_cb(cid, "Please /start first.", alert=True)
        return

    answer_cb(cid)  # acknowledge immediately

    # Parse callback data: rtype:action:rid[:value]
    parts = data.split(":", 3)
    if len(parts) < 3:
        return
    rtype  = parts[0]
    action = parts[1]
    rid    = parts[2]
    value  = parts[3] if len(parts) == 4 else ""

    # ── Tasks ──────────────────────────────────────────────────────────────────
    if rtype == "task":
        if action == "done":
            _cb_task_done(chat_id, rid, msg_id)
        elif action == "status":
            edit_msg(chat_id, msg_id, "📋 Select new status:",
                     _status_keyboard("task", rid, _TASK_STATUSES))
        elif action == "setstatus":
            _cb_task_setstatus(chat_id, rid, value, msg_id)
        elif action == "note":
            save_session(chat_id, "note", "task", rid, "note")
            force_reply(chat_id, f"📝 Enter note for task *#{rid}*:")
        elif action == "delete":
            t = query_one("SELECT title FROM tasks WHERE id=%s", (rid,))
            title = t["title"] if t else f"#{rid}"
            edit_msg(chat_id, msg_id,
                     f"🗑 Delete task *{title}*?\nThis cannot be undone.",
                     [[{"text": "Yes, delete", "callback_data": f"task:delete_confirm:{rid}"},
                       {"text": "No, keep",    "callback_data": f"task:back:{rid}"}]])
        elif action == "delete_confirm":
            _cb_task_delete(chat_id, rid, msg_id)
        elif action == "setpriority":
            _handle_task_setpriority(chat_id, value)
        elif action == "setassign":
            _handle_task_setassign(chat_id, value)
        elif action == "back":
            t = query_one("SELECT * FROM tasks WHERE id=%s", (rid,))
            if t:
                edit_msg(chat_id, msg_id, _task_text(t), task_keyboard(rid))

    # ── Quotations ─────────────────────────────────────────────────────────────
    elif rtype == "quot":
        if action == "status":
            edit_msg(chat_id, msg_id, "📋 Select new status:",
                     _status_keyboard("quot", rid, _QUOT_STATUSES))
        elif action == "setstatus":
            _cb_quot_setstatus(chat_id, rid, value, msg_id)
        elif action == "payment":
            save_session(chat_id, "payment", "quotation", rid, "amount")
            q = query_one("SELECT quotation_no, customer_name FROM quotations WHERE id=%s", (rid,))
            lbl = f"{q['quotation_no']} — {q['customer_name']}" if q else rid
            force_reply(chat_id, f"💰 Amount paid (UGX) for _{lbl}_:")
        elif action == "note":
            save_session(chat_id, "note", "quotation", rid, "note")
            force_reply(chat_id, "📝 Enter note for this quotation:")
        elif action == "back":
            q = query_one("SELECT * FROM quotations WHERE id=%s", (rid,))
            if q:
                edit_msg(chat_id, msg_id, _quot_text(q), quot_keyboard(rid))

    # ── Maintenance ────────────────────────────────────────────────────────────
    elif rtype == "maint":
        if action == "status":
            edit_msg(chat_id, msg_id, "📋 Select new status:",
                     _status_keyboard("maint", rid, _MAINT_STATUSES))
        elif action == "setstatus":
            _cb_maint_setstatus(chat_id, rid, value, msg_id)
        elif action == "note":
            save_session(chat_id, "note", "maintenance", rid, "note")
            force_reply(chat_id, f"📝 Enter note for maintenance job *#{rid}*:")
        elif action == "back":
            m = query_one("SELECT * FROM maintenance_records WHERE id=%s", (rid,))
            if m:
                edit_msg(chat_id, msg_id, _maint_text(m), maint_keyboard(rid))

    # ── Receipts ───────────────────────────────────────────────────────────────
    elif rtype == "rcpt":
        if action == "pickquot":
            # rid = quotation id
            q = query_one(
                "SELECT quotation_no, customer_name FROM quotations WHERE id=%s", (rid,))
            lbl = f"{q['quotation_no']} — {q['customer_name']}" if q else rid
            save_session(chat_id, "receipt_create", "receipt", "",
                         "amount", data={"quotation_id": rid, "label": lbl})
            force_reply(chat_id, f"💰 Amount paid (UGX) for _{lbl}_:")

    # ── Balancing ──────────────────────────────────────────────────────────────
    elif rtype == "bal":
        if action == "spend":
            save_session(chat_id, "bal_spend", "balancing", rid, "description")
            force_reply(chat_id, "💸 Description of expense:")
        elif action == "settle_start":
            # Ask who is paying
            send(chat_id, "🤝 Who is making the settlement payment?",
                 [[{"text": "Hillary → Dennis",
                    "callback_data": f"bal:settle_from:{rid}:Hillary"},
                   {"text": "Dennis → Hillary",
                    "callback_data": f"bal:settle_from:{rid}:Dennis"}]])
        elif action == "settle_from":
            # value = from_person
            save_session(chat_id, "bal_settle", "balancing", rid,
                         "amount", data={"from_person": value})
            force_reply(chat_id, f"💰 Settlement amount (UGX) from *{value}*:")
        elif action == "spend_by":
            # value = paid_by — finalize the spend
            sess = get_session(chat_id)
            if sess:
                d = _session_data(sess)
                d["paid_by"] = value
                _finalize_bal_spend(chat_id, sess["record_id"], d)

    # ── Payment method picker (shared across payment + receipt flows) ───────────
    elif rtype == "paymethod":
        # value = Cash | Mobile Money | EFT
        sess = get_session(chat_id)
        if not sess:
            send(chat_id, "Session expired. Please start again.")
            return
        d = _session_data(sess)
        d["method"] = value
        ctx = sess.get("context", "")
        if ctx == "payment":
            _finalize_payment(chat_id, sess["record_id"], d)
        elif ctx == "receipt_create":
            _finalize_receipt(chat_id, d, person)


# ══════════════════════════════════════════════════════════════════════════════
# Session reply handler  (ForceReply responses)
# ══════════════════════════════════════════════════════════════════════════════

def _handle_session_reply(chat_id, text: str, sess, person: str):
    context = sess.get("context", "")
    rtype   = sess.get("record_type", "")
    rid     = sess.get("record_id", "")
    step    = sess.get("step", "")
    d       = _session_data(sess)

    # ── Simple single-field updates ────────────────────────────────────────────
    if context == "note":
        if rtype == "task":
            execute("UPDATE tasks SET notes=%s, updated_at=NOW() WHERE id=%s", (text, rid))
            send(chat_id, f"✅ Note saved on task *#{rid}*.")
        elif rtype == "quotation":
            execute("UPDATE quotations SET notes=%s, updated_at=NOW() WHERE id=%s", (text, rid))
            send(chat_id, "✅ Note saved on quotation.")
        elif rtype == "maintenance":
            execute("UPDATE maintenance_records SET notes=%s WHERE id=%s", (text, rid))
            send(chat_id, f"✅ Note saved on job *#{rid}*.")
        clear_session(chat_id)
        return

    if context == "cancel_reason":
        execute("""UPDATE maintenance_records
                   SET cancellation_reason=%s, status='Cancelled'
                   WHERE id=%s""", (text, rid))
        send(chat_id, f"✅ Job *#{rid}* cancelled. Reason recorded.")
        clear_session(chat_id)
        return

    # ── Task creation flow ─────────────────────────────────────────────────────
    if context == "task_create":
        if step == "title":
            d["title"] = text
            save_session(chat_id, "task_create", "task", "", "due_date", data=d)
            force_reply(chat_id,
                        f"📅 Due date (YYYY-MM-DD) or `-` to skip:\n_e.g. {date.today()}_")
        elif step == "due_date":
            d["due_date"] = "" if text == "-" else text
            save_session(chat_id, "task_create", "task", "", "priority", data=d)
            send(chat_id, "🎯 Priority?",
                 [[{"text": "🚨 Urgent", "callback_data": f"task:setpriority:__new__:Urgent"},
                   {"text": "🔴 High",   "callback_data": f"task:setpriority:__new__:High"}],
                  [{"text": "🟡 Normal", "callback_data": f"task:setpriority:__new__:Normal"},
                   {"text": "⚪ Low",    "callback_data": f"task:setpriority:__new__:Low"}]])
        elif step == "assigned_to":
            d["assigned_to"] = text.title() if text.title() in ["Hillary", "Dennis"] else person.title()
            _finalize_task_create(chat_id, d)
        return

    # ── Maintenance creation flow ──────────────────────────────────────────────
    if context == "maint_create":
        if step == "client_name":
            d["client_name"] = text
            save_session(chat_id, "maint_create", "maintenance", "", "client_phone", data=d)
            force_reply(chat_id, "📞 Client phone (or `-` to skip):")
        elif step == "client_phone":
            d["client_phone"] = "" if text == "-" else text
            save_session(chat_id, "maint_create", "maintenance", "", "visit_date", data=d)
            force_reply(chat_id,
                        f"📅 Visit date (YYYY-MM-DD) or `-` for today ({date.today()}):")
        elif step == "visit_date":
            d["visit_date"] = date.today().isoformat() if text == "-" else text
            save_session(chat_id, "maint_create", "maintenance", "", "problem", data=d)
            force_reply(chat_id, "🔧 Describe the problem:")
        elif step == "problem":
            d["problem"] = text
            _finalize_maint_create(chat_id, d, person)
        return

    # ── Payment amount ─────────────────────────────────────────────────────────
    if context == "payment" and step == "amount":
        try:
            d["amount"] = float(text.replace(",", "").replace(" ", ""))
        except ValueError:
            force_reply(chat_id, "❌ Invalid amount. Numbers only (e.g. 500000):")
            return
        save_session(chat_id, "payment", "quotation", rid, "method", data=d)
        send(chat_id, "💳 Payment method?",
             [[{"text": "Cash",         "callback_data": f"paymethod:x:{rid}:Cash"},
               {"text": "Mobile Money", "callback_data": f"paymethod:x:{rid}:Mobile Money"},
               {"text": "EFT",          "callback_data": f"paymethod:x:{rid}:EFT"}]])
        return

    # ── Receipt amount ─────────────────────────────────────────────────────────
    if context == "receipt_create" and step == "amount":
        try:
            d["amount"] = float(text.replace(",", "").replace(" ", ""))
        except ValueError:
            force_reply(chat_id, "❌ Invalid amount. Numbers only:")
            return
        save_session(chat_id, "receipt_create", "receipt", "", "method", data=d)
        send(chat_id, "💳 Payment method?",
             [[{"text": "Cash",         "callback_data": "paymethod:x:__rcpt__:Cash"},
               {"text": "Mobile Money", "callback_data": "paymethod:x:__rcpt__:Mobile Money"},
               {"text": "EFT",          "callback_data": "paymethod:x:__rcpt__:EFT"}]])
        return

    # ── Balancing spend flow ───────────────────────────────────────────────────
    if context == "bal_spend":
        if step == "description":
            d["description"] = text
            save_session(chat_id, "bal_spend", "balancing", rid, "amount", data=d)
            force_reply(chat_id, "💰 Amount (UGX):")
        elif step == "amount":
            try:
                d["amount"] = float(text.replace(",", "").replace(" ", ""))
            except ValueError:
                force_reply(chat_id, "❌ Invalid amount. Numbers only:")
                return
            save_session(chat_id, "bal_spend", "balancing", rid, "paid_by", data=d)
            send(chat_id, "👤 Paid by?",
                 [[{"text": "Hillary", "callback_data": f"bal:spend_by:{rid}:Hillary"},
                   {"text": "Dennis",  "callback_data": f"bal:spend_by:{rid}:Dennis"}]])
        return

    # ── Balancing settlement flow ──────────────────────────────────────────────
    if context == "bal_settle":
        if step == "amount":
            try:
                d["amount"] = float(text.replace(",", "").replace(" ", ""))
            except ValueError:
                force_reply(chat_id, "❌ Invalid amount. Numbers only:")
                return
            save_session(chat_id, "bal_settle", "balancing", rid, "notes", data=d)
            force_reply(chat_id, "📝 Notes for this settlement (or `-` to skip):")
        elif step == "notes":
            notes = "" if text == "-" else text
            _finalize_settlement(chat_id, rid, d, notes)
        return


# ══════════════════════════════════════════════════════════════════════════════
# Callback action handlers
# ══════════════════════════════════════════════════════════════════════════════

def _cb_task_done(chat_id, tid, msg_id):
    from utils.notify import notify_task
    execute("UPDATE tasks SET status='Done', updated_at=NOW() WHERE id=%s", (tid,))
    t = query_one("SELECT * FROM tasks WHERE id=%s", (tid,))
    edit_msg(chat_id, msg_id,
             f"✅ *Task #{tid} marked Done.*\n_{t['title'] if t else ''}_")
    if t:
        notify_task(dict(t), action="completed")


def _cb_task_setstatus(chat_id, tid, status, msg_id):
    from utils.notify import notify_task
    execute("UPDATE tasks SET status=%s, updated_at=NOW() WHERE id=%s", (status, tid))
    t = query_one("SELECT * FROM tasks WHERE id=%s", (tid,))
    edit_msg(chat_id, msg_id,
             _task_text(t) if t else f"Task #{tid} → {status}",
             task_keyboard(tid))
    if t:
        notify_task(dict(t), action="updated")


def _cb_task_delete(chat_id, tid, msg_id):
    t = query_one("SELECT title FROM tasks WHERE id=%s", (tid,))
    execute("DELETE FROM tasks WHERE id=%s", (tid,))
    edit_msg(chat_id, msg_id,
             f"🗑 Task *{t['title'] if t else f'#{tid}'}* deleted.")


def _cb_quot_setstatus(chat_id, qid, status, msg_id):
    from utils.notify import notify_quotation_status
    execute("UPDATE quotations SET status=%s, updated_at=NOW() WHERE id=%s", (status, qid))
    q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    text = _quot_text(q) if q else f"Quotation → {status}"
    has_contact = q and ((q.get("customer_email") or "").strip() or (q.get("customer_phone") or "").strip())
    if q and status in ("Pending", "Approved") and has_contact:
        text += "\n\n⚠️ Customer NOT notified from here — resend from the web app to email/WhatsApp them the PDF."
    edit_msg(chat_id, msg_id, text, quot_keyboard(qid))
    if q:
        notify_quotation_status(dict(q), status)


def _cb_maint_setstatus(chat_id, mid, status, msg_id):
    from utils.notify import notify_maintenance
    if status == "Cancelled":
        save_session(chat_id, "cancel_reason", "maintenance", mid, "cancel_reason")
        force_reply(chat_id, f"❌ Reason for cancelling job *#{mid}*:")
        return
    execute("UPDATE maintenance_records SET status=%s WHERE id=%s", (status, mid))
    m = query_one("SELECT * FROM maintenance_records WHERE id=%s", (mid,))
    edit_msg(chat_id, msg_id,
             _maint_text(m) if m else f"Job #{mid} → {status}",
             maint_keyboard(mid))
    if m:
        notify_maintenance(dict(m), action="updated")


# ══════════════════════════════════════════════════════════════════════════════
# Finalizers
# ══════════════════════════════════════════════════════════════════════════════

def _finalize_task_create(chat_id, d):
    from utils.notify import notify_task
    execute("""INSERT INTO tasks (title, description, due_date, priority, status, assigned_to, notes)
               VALUES (%s, '', %s, %s, 'Pending', %s, '')""",
            (d["title"],
             d.get("due_date") or None,
             d.get("priority", "Normal"),
             d.get("assigned_to", "")))
    t = query_one("SELECT * FROM tasks ORDER BY id DESC LIMIT 1")
    clear_session(chat_id)
    send(chat_id,
         f"✅ Task created: *{d['title']}*\n"
         f"Priority: {d.get('priority','Normal')}  |  Assigned: {d.get('assigned_to','—')}")
    if t:
        notify_task(dict(t), action="created")


def _finalize_maint_create(chat_id, d, person):
    from utils.notify import notify_maintenance
    execute("""INSERT INTO maintenance_records
               (client_name, client_phone, visit_date, type, problem, status,
                executor_name, parts_cost, labour_fee, executor_payment, h_ratio, d_ratio)
               VALUES (%s,%s,%s,'Paid',%s,'Open',%s,0,0,0,100,0)""",
            (d["client_name"],
             d.get("client_phone", ""),
             d.get("visit_date", date.today().isoformat()),
             d.get("problem", ""),
             person.title()))
    m = query_one("SELECT * FROM maintenance_records ORDER BY id DESC LIMIT 1")
    clear_session(chat_id)
    send(chat_id, f"✅ Maintenance job created for *{d['client_name']}*.")
    if m:
        notify_maintenance(dict(m), action="created")


def _finalize_payment(chat_id, qid, d):
    amount = d.get("amount", 0)
    method = d.get("method", "Cash")
    execute("""INSERT INTO payments (quotation_id, date, amount, method, notes)
               VALUES (%s,%s,%s,%s,'')""",
            (qid, date.today().isoformat(), amount, method))
    q = query_one("SELECT quotation_no, customer_name FROM quotations WHERE id=%s", (qid,))
    label = f"{q['quotation_no']} — {q['customer_name']}" if q else qid
    clear_session(chat_id)
    send(chat_id,
         f"✅ Payment of *UGX {amount:,.0f}* ({method}) recorded for _{label}_.")


def _finalize_receipt(chat_id, d, person):
    from utils.notify import notify_receipt
    import uuid
    amount  = d.get("amount", 0)
    method  = d.get("method", "Cash")
    qid     = d.get("quotation_id") or None
    label   = d.get("label", "")

    # Auto-generate receipt number
    yr   = date.today().year
    last = query_one(
        "SELECT receipt_no FROM receipts WHERE receipt_no LIKE %s "
        "ORDER BY receipt_no DESC LIMIT 1", (f"RCT-{yr}-%",))
    if last:
        try:
            rno = f"RCT-{yr}-{int(last['receipt_no'].rsplit('-', 1)[-1]) + 1:03d}"
        except Exception:
            rno = f"RCT-{yr}-001"
    else:
        rno = f"RCT-{yr}-001"

    # Pull customer info from linked quotation
    q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,)) if qid else None
    cname = q["customer_name"] if q else "Unknown"
    cphone = q["customer_phone"] if q else ""

    rid = str(uuid.uuid4())
    execute("""INSERT INTO receipts
               (id, receipt_no, date, customer_name, customer_phone,
                being_for, amount_fig, amount_paid, balance,
                payment_method, issued_name, received_name, quotation_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, rno, date.today().isoformat(), cname, cphone,
             label, amount, amount, 0,
             method, person.title(), cname, qid))

    r = query_one("SELECT * FROM receipts WHERE id=%s", (rid,))
    clear_session(chat_id)
    send(chat_id,
         f"✅ Receipt *{rno}* created\n"
         f"Client: {cname}  |  UGX {amount:,.0f} ({method})\n"
         f"[🔗 Open]({_APP_URL}/receipts/{rid})")
    if r:
        notify_receipt(dict(r))


def _finalize_bal_spend(chat_id, jid, d):
    execute("""INSERT INTO balancing_spend_lines
               (balancing_job_id, paid_by, description, amount, date)
               VALUES (%s,%s,%s,%s,%s)""",
            (jid, d["paid_by"], d["description"],
             d["amount"], date.today().isoformat()))
    clear_session(chat_id)
    send(chat_id,
         f"✅ Spend of *UGX {d['amount']:,.0f}* ({d['description']}) "
         f"recorded — paid by {d['paid_by']}.")


def _finalize_settlement(chat_id, jid, d, notes):
    from utils.notify import notify_settlement
    amount      = d.get("amount", 0)
    from_person = d.get("from_person", "Hillary")
    to_person   = "Dennis" if from_person.lower() == "hillary" else "Hillary"
    execute("""INSERT INTO balancing_settlements
               (balancing_job_id, date, amount, from_person, notes)
               VALUES (%s,%s,%s,%s,%s)""",
            (jid, date.today().isoformat(), amount, from_person, notes))
    job = query_one("SELECT bj.*, q.quotation_no FROM balancing_jobs bj "
                    "LEFT JOIN quotations q ON q.id=bj.linked_quotation_id "
                    "WHERE bj.id=%s", (jid,))
    clear_session(chat_id)
    send(chat_id,
         f"✅ Settlement of *UGX {amount:,.0f}* recorded.\n"
         f"{from_person} → {to_person}")
    if job:
        notify_settlement(dict(job), amount=amount,
                          from_person=from_person, to_person=to_person, notes=notes)


# ══════════════════════════════════════════════════════════════════════════════
# Callback: task priority during creation (buttons, not ForceReply)
# ══════════════════════════════════════════════════════════════════════════════
# These are handled inside _handle_callback via rtype="task", action="setpriority"
# — we need to add them. Patch into _handle_callback's task section:

def _handle_task_setpriority(chat_id, value):
    """Called when priority button is tapped during task creation."""
    sess = get_session(chat_id)
    if not sess or sess.get("context") != "task_create":
        return
    d = _session_data(sess)
    d["priority"] = value
    save_session(chat_id, "task_create", "task", "", "assigned_to", data=d)
    send(chat_id, "👤 Assign to?",
         [[{"text": "Hillary", "callback_data": "task:setassign:__new__:Hillary"},
           {"text": "Dennis",  "callback_data": "task:setassign:__new__:Dennis"}]])


def _handle_task_setassign(chat_id, value):
    """Called when assignee button is tapped during task creation."""
    sess = get_session(chat_id)
    if not sess or sess.get("context") != "task_create":
        return
    d = _session_data(sess)
    d["assigned_to"] = value
    _finalize_task_create(chat_id, d)


# ══════════════════════════════════════════════════════════════════════════════
# Command handlers
# ══════════════════════════════════════════════════════════════════════════════

def _cmd_start(chat_id, username):
    if get_person(chat_id):
        send(chat_id, f"✅ Already registered. Send /help")
        return
    send(chat_id, "👋 Welcome to *Rincol ERP*.\nWho are you?",
         [[{"text": "Hillary", "callback_data": "register:hillary"},
           {"text": "Dennis",  "callback_data": "register:dennis"}]])


def _cmd_help(chat_id):
    send(chat_id,
         "*Rincol ERP Bot — Commands*\n\n"
         "*📋 Tasks*\n"
         "/mytasks — your open tasks\n"
         "/tasks — all open tasks\n"
         "/newtask — create a task\n\n"
         "*📄 Quotations*\n"
         "/quotations — active quotations\n\n"
         "*🔧 Maintenance*\n"
         "/maintenance — open jobs\n"
         "/newjob — log a maintenance job\n\n"
         "*💰 Receipts*\n"
         "/receipts — recent receipts\n"
         "/newreceipt — create a receipt\n\n"
         "*📊 Balancing*\n"
         "/balancing — active jobs\n\n"
         "*📅 Dashboard*\n"
         "/today — due today\n"
         "/summary — counts overview")


def _cmd_mytasks(chat_id, person):
    rows = query("""SELECT * FROM tasks
                    WHERE LOWER(assigned_to)=%s AND status != 'Done'
                    ORDER BY due_date NULLS LAST, id DESC LIMIT 10""", (person,))
    if not rows:
        send(chat_id, "✅ No open tasks assigned to you.")
        return
    for t in rows:
        send(chat_id, _task_text(t), task_keyboard(t["id"]))


def _cmd_tasks(chat_id):
    rows = query("""SELECT * FROM tasks WHERE status != 'Done'
                    ORDER BY due_date NULLS LAST, id DESC LIMIT 10""")
    if not rows:
        send(chat_id, "✅ No open tasks.")
        return
    for t in rows:
        send(chat_id, _task_text(t), task_keyboard(t["id"]))


def _cmd_quotations(chat_id):
    rows = query("""SELECT * FROM quotations
                    WHERE status NOT IN ('Completed','Cancelled')
                    ORDER BY date DESC LIMIT 8""")
    if not rows:
        send(chat_id, "No active quotations.")
        return
    for q in rows:
        send(chat_id, _quot_text(q), quot_keyboard(q["id"]))


def _cmd_maintenance(chat_id):
    rows = query("""SELECT * FROM maintenance_records
                    WHERE status NOT IN ('Resolved','Cancelled')
                    ORDER BY visit_date NULLS LAST, id DESC LIMIT 8""")
    if not rows:
        send(chat_id, "No open maintenance jobs.")
        return
    for m in rows:
        send(chat_id, _maint_text(m), maint_keyboard(m["id"]))


def _cmd_receipts(chat_id):
    rows = query("SELECT * FROM receipts ORDER BY date DESC LIMIT 8")
    if not rows:
        send(chat_id, "No receipts yet.")
        return
    lines = ["*Recent Receipts*\n"]
    for r in rows:
        lines.append(
            f"💰 *{r['receipt_no']}* — {r['customer_name']} "
            f"— UGX {(r.get('amount_paid') or 0):,.0f}"
        )
    send(chat_id, "\n".join(lines))


def _cmd_balancing(chat_id):
    rows = query("SELECT * FROM balancing_jobs ORDER BY date DESC LIMIT 6")
    if not rows:
        send(chat_id, "No balancing jobs.")
        return
    for j in rows:
        text = (f"📊 *{j['job_name']}*\n"
                f"Quoted: UGX {(j.get('quoted') or 0):,.0f}\n"
                f"Split: Hillary {j.get('h_ratio', 60)}% / "
                f"Dennis {j.get('d_ratio', 40)}%")
        kbd = [
            [{"text": "➕ Add Spend",   "callback_data": f"bal:spend:{j['id']}"},
             {"text": "🤝 Settle",      "callback_data": f"bal:settle_start:{j['id']}"}],
            [{"text": "🔗 Open",        "url": f"{_APP_URL}/balancing/{j['id']}"}],
        ]
        send(chat_id, text, kbd)


def _cmd_newtask(chat_id):
    clear_session(chat_id)
    save_session(chat_id, "task_create", "task", "", "title")
    force_reply(chat_id, "📋 *New Task*\n\nWhat's the title?")


def _cmd_newjob(chat_id):
    clear_session(chat_id)
    save_session(chat_id, "maint_create", "maintenance", "", "client_name")
    force_reply(chat_id, "🔧 *New Maintenance Job*\n\nClient name?")


def _cmd_newreceipt(chat_id):
    rows = query("""SELECT id, quotation_no, customer_name
                    FROM quotations
                    WHERE status NOT IN ('Cancelled')
                    ORDER BY date DESC LIMIT 20""")
    if not rows:
        send(chat_id, "No quotations found to link receipt to.")
        return
    # Build button grid — 1 per row (names can be long)
    kbd = [[{"text": f"{q['quotation_no']} — {q['customer_name']}",
             "callback_data": f"rcpt:pickquot:{q['id']}"}]
           for q in rows]
    send(chat_id, "💰 *New Receipt*\n\nSelect quotation:", kbd)


def _cmd_today(chat_id):
    today = date.today().isoformat()
    tasks = query(
        "SELECT * FROM tasks WHERE due_date=%s AND status != 'Done' ORDER BY priority",
        (today,))
    maint = query(
        "SELECT * FROM maintenance_records "
        "WHERE visit_date=%s AND status NOT IN ('Resolved','Cancelled')",
        (today,))
    lines = [f"📅 *Today — {today}*\n"]
    if tasks:
        lines.append("*Tasks due today:*")
        for t in tasks:
            p = _PRIORITY_EMOJI.get(t.get("priority", "Normal"), "🟡")
            lines.append(f"  {p} {t['title']} → {t.get('assigned_to','—')}")
    else:
        lines.append("_No tasks due today._")
    if maint:
        lines.append("\n*Maintenance visits:*")
        for m in maint:
            lines.append(f"  🔧 {m['client_name']} — {(m.get('problem') or '—')[:50]}")
    else:
        lines.append("_No maintenance visits today._")
    send(chat_id, "\n".join(lines))


def _cmd_summary(chat_id):
    open_tasks = query_one("SELECT COUNT(*) AS c FROM tasks WHERE status != 'Done'")
    pend_quots = query_one(
        "SELECT COUNT(*) AS c FROM quotations WHERE status NOT IN ('Completed','Cancelled')")
    open_maint = query_one(
        "SELECT COUNT(*) AS c FROM maintenance_records "
        "WHERE status NOT IN ('Resolved','Cancelled')")
    month_recv = query_one(
        "SELECT COALESCE(SUM(amount_paid),0) AS total FROM receipts "
        "WHERE date >= NOW() - INTERVAL '30 days'")
    send(chat_id,
         f"📊 *Rincol ERP — Summary*\n\n"
         f"📋 Open tasks: *{(open_tasks or {}).get('c', 0)}*\n"
         f"📄 Active quotations: *{(pend_quots or {}).get('c', 0)}*\n"
         f"🔧 Open maintenance: *{(open_maint or {}).get('c', 0)}*\n"
         f"💰 Receipts (30 days): *UGX {(month_recv or {}).get('total', 0):,.0f}*")
