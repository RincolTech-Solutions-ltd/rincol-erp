"""Rincol Web ERP — Flask Application."""
import os
import io
import json
import math
import uuid
from datetime import date, datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_file, jsonify, abort)
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_ANON_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

from utils.db import query, query_one, execute, next_quotation_number, close_db
from utils.pdf import build_quotation_pdf, build_receipt_pdf, build_statement_pdf
from utils.notify import (notify_maintenance, notify_quotation,
                           notify_quotation_status, notify_receipt,
                           notify_task, notify_settlement, notify_balancing_job,
                           send_customer_statement)
from utils.tg_bot import handle_update as _tg_handle_update


@app.teardown_appcontext
def _teardown_db(exc):
    close_db(error=exc is not None)

# Default signature — always included on quotation PDFs
_DEFAULT_SIG_PATH = os.path.join(os.path.dirname(__file__), "static", "img", "signature.png")

def _load_default_sig():
    """Return signature bytes if the file exists, else None."""
    try:
        with open(_DEFAULT_SIG_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth_login"))
        return f(*args, **kwargs)
    return decorated


def current_user():
    return session.get("user", {})


app.jinja_env.globals["current_user"] = current_user


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def auth_login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form["email"].strip()
        password = request.form["password"]
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session["user"] = {
                "id":    res.user.id,
                "email": res.user.email,
                "name":  res.user.user_metadata.get("full_name", email.split("@")[0]),
            }
            session["sb_access_token"]  = res.session.access_token
            session["sb_refresh_token"] = res.session.refresh_token
            return redirect(url_for("dashboard"))
        except Exception as e:
            flash(str(e), "danger")
    return render_template("auth/login.html")


@app.route("/logout")
def auth_logout():
    session.clear()
    return redirect(url_for("auth_login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    stats = {
        "quotations":  query_one("SELECT COUNT(*) AS n FROM quotations")["n"],
        "draft":       query_one("SELECT COUNT(*) AS n FROM quotations WHERE status='Draft'")["n"],
        "pending":     query_one("SELECT COUNT(*) AS n FROM quotations WHERE status='Pending'")["n"],
        "outstanding": query_one(
            "SELECT COALESCE(SUM(q.total_amount - COALESCE(r.paid,0)),0) AS n "
            "FROM quotations q "
            "LEFT JOIN (SELECT quotation_id, SUM(amount_paid) AS paid FROM receipts "
            "           WHERE quotation_id IS NOT NULL GROUP BY quotation_id) r "
            "  ON r.quotation_id=q.id "
            "WHERE q.status NOT IN ('Cancelled','Pending')")["n"],
        "maintenance": query_one("SELECT COUNT(*) AS n FROM maintenance_records WHERE status IN ('Scheduled','Open','In Progress','Pending Parts')")["n"],
        "tasks_due":   query_one(
            "SELECT COUNT(*) AS n FROM tasks WHERE status != 'Done' AND due_date <= CURRENT_DATE + 3")["n"],
    }
    recent = query(
        "SELECT id, quotation_no, customer_name, total_amount, status, date "
        "FROM quotations ORDER BY created_at DESC LIMIT 8")
    active_jobs = query(
        "SELECT q.id, q.quotation_no, q.customer_name, q.customer_address, "
        "       q.date, q.status, q.total_amount, e.executor_name "
        "FROM quotations q "
        "LEFT JOIN ("
        "  SELECT DISTINCT ON (quotation_id) quotation_id, executor_name "
        "  FROM job_executions ORDER BY quotation_id, execution_date DESC NULLS LAST"
        ") e ON e.quotation_id = q.id "
        "WHERE q.status IN ('Approved','In Progress') "
        "ORDER BY q.date ASC")
    overdue_tasks = query(
        "SELECT id, title, due_date, priority FROM tasks "
        "WHERE status != 'Done' AND due_date < CURRENT_DATE ORDER BY due_date LIMIT 5")
    unbalanced_jobs = query("""
        SELECT q.id, q.quotation_no, q.customer_name, q.total_amount, q.date,
               je.executor_name, je.execution_date
        FROM quotations q
        LEFT JOIN LATERAL (
            SELECT executor_name, execution_date FROM job_executions
            WHERE quotation_id = q.id ORDER BY execution_date DESC NULLS LAST LIMIT 1
        ) je ON true
        WHERE q.status = 'Completed'
          AND q.id NOT IN (
              SELECT linked_quotation_id FROM balancing_jobs
              WHERE linked_quotation_id IS NOT NULL
          )
        ORDER BY q.date DESC
    """)
    return render_template("dashboard.html", stats=stats, recent=recent,
                           active_jobs=active_jobs, overdue_tasks=overdue_tasks,
                           unbalanced_jobs=unbalanced_jobs)


# ── Quotations ────────────────────────────────────────────────────────────────
@app.route("/quotations")
@login_required
def quotations_list():
    status  = request.args.get("status", "")
    payment = request.args.get("payment", "")
    search  = request.args.get("q", "")
    sql     = ("SELECT q.id, q.quotation_no, q.customer_name, q.customer_phone, "
               "q.total_amount, q.status, q.date, COALESCE(r.paid, 0) AS paid "
               "FROM quotations q "
               "LEFT JOIN (SELECT quotation_id, SUM(amount_paid) AS paid FROM receipts "
               "           WHERE quotation_id IS NOT NULL GROUP BY quotation_id) r "
               "ON r.quotation_id = q.id WHERE 1=1")
    params  = []
    if status:
        sql += " AND q.status=%s"; params.append(status)
    if search:
        sql += " AND (q.customer_name ILIKE %s OR q.quotation_no ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if payment == "unpaid":
        sql += " AND COALESCE(r.paid, 0) <= 0 AND q.status != 'Cancelled'"
    elif payment == "partial":
        sql += " AND COALESCE(r.paid, 0) > 0 AND COALESCE(r.paid, 0) < q.total_amount AND q.status != 'Cancelled'"
    elif payment == "paid":
        sql += " AND COALESCE(r.paid, 0) >= q.total_amount AND q.status != 'Cancelled'"
    sql += " ORDER BY q.created_at DESC"
    rows = query(sql, params)
    return render_template("quotation/list.html", quotations=rows,
                           status=status, payment=payment, search=search)


@app.route("/quotations/new", methods=["GET", "POST"])
@login_required
def quotations_new():
    templates = query("SELECT id, name FROM system_templates ORDER BY sort_order")
    catalog   = query("SELECT id, category, name, spec, uom, sell_price FROM catalog_items ORDER BY category, name")
    if request.method == "POST":
        return _save_quotation(None)
    return render_template("quotation/form.html", q=None, templates=templates, catalog=catalog,
                           qno=next_quotation_number(), today=date.today().isoformat())


@app.route("/quotations/<qid>", methods=["GET"])
@login_required
def quotations_view(qid):
    q     = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    if not q:
        abort(404)
    items    = query("SELECT * FROM quotation_items WHERE quotation_id=%s ORDER BY line_no", (qid,))
    receipts = query("SELECT * FROM receipts WHERE quotation_id=%s ORDER BY date DESC", (qid,))
    execs    = query("SELECT * FROM job_executions WHERE quotation_id=%s ORDER BY execution_date DESC", (qid,))
    paid     = sum(r["amount_paid"] for r in receipts)
    balance  = (q["total_amount"] or 0) - paid
    _default_executors = ['Hillary', 'Dennis']
    _extra_exec = query("SELECT DISTINCT executor_name FROM job_executions WHERE executor_name IS NOT NULL AND executor_name != '' ORDER BY executor_name")
    executor_names = list(dict.fromkeys(_default_executors + [r['executor_name'] for r in _extra_exec if r['executor_name'] not in _default_executors]))
    return render_template("quotation/view.html", q=q, items=items,
                           receipts=receipts, execs=execs, paid=paid, balance=balance,
                           executor_names=executor_names)


@app.route("/quotations/<qid>/edit", methods=["GET", "POST"])
@login_required
def quotations_edit(qid):
    q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    if not q:
        abort(404)
    if request.method == "POST":
        return _save_quotation(qid)
    items     = query("SELECT * FROM quotation_items WHERE quotation_id=%s ORDER BY line_no", (qid,))
    templates = query("SELECT id, name FROM system_templates ORDER BY sort_order")
    catalog   = query("SELECT id, category, name, spec, uom, sell_price FROM catalog_items ORDER BY category, name")
    return render_template("quotation/form.html", q=q, items=items,
                           templates=templates, catalog=catalog)


def _save_quotation(qid):
    f          = request.form
    _is_new    = qid is None
    qid        = qid or str(uuid.uuid4())
    qno = f.get("quotation_no") or next_quotation_number()

    descs  = f.getlist("desc[]")
    uoms   = f.getlist("uom[]")
    qtys   = f.getlist("qty[]")
    prices = f.getlist("price[]")

    items = []
    subtotal = 0.0
    for i, (d, u, q, p) in enumerate(zip(descs, uoms, qtys, prices), 1):
        if not d.strip():
            continue
        qty_v   = float(q or 0)
        price_v = float(p or 0)
        total   = qty_v * price_v
        subtotal += total
        items.append((qid, i, d.strip(), u or "pc", qty_v, price_v, total))

    apply_vat = f.get("apply_vat") == "1"
    vat_rate  = float(f.get("vat_rate") or 18) if apply_vat else None
    vat_amt   = subtotal * vat_rate / 100 if vat_rate else 0
    grand     = round(subtotal + vat_amt, 2)

    _cid = f.get("customer_id", "").strip()
    customer_id = _cid if _cid and _cid != "None" else None

    execute("""
        INSERT INTO quotations (id, quotation_no, date, title, customer_name, customer_phone,
            customer_email, customer_address, delivery, validity, warranty,
            payment_terms, status, total_amount, vat_rate, notes, customer_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
            quotation_no=EXCLUDED.quotation_no, date=EXCLUDED.date,
            title=EXCLUDED.title, customer_name=EXCLUDED.customer_name,
            customer_phone=EXCLUDED.customer_phone, customer_email=EXCLUDED.customer_email,
            customer_address=EXCLUDED.customer_address, delivery=EXCLUDED.delivery,
            validity=EXCLUDED.validity, warranty=EXCLUDED.warranty,
            payment_terms=EXCLUDED.payment_terms, status=EXCLUDED.status,
            total_amount=EXCLUDED.total_amount, vat_rate=EXCLUDED.vat_rate,
            notes=EXCLUDED.notes, customer_id=EXCLUDED.customer_id, updated_at=NOW()
    """, (qid, qno, f.get("date") or date.today().isoformat(),
          f.get("title","Quotation"), f["customer_name"], f.get("customer_phone",""),
          f.get("customer_email",""), f.get("customer_address",""),
          f.get("delivery",""), f.get("validity","30 days"), f.get("warranty",""),
          f.get("payment_terms","Cash / MM / EFT"), f.get("status","Draft"),
          grand, vat_rate, f.get("notes",""), customer_id))

    execute("DELETE FROM quotation_items WHERE quotation_id=%s", (qid,))
    for it in items:
        execute("INSERT INTO quotation_items (quotation_id,line_no,description,uom,qty,unit_price,total) VALUES (%s,%s,%s,%s,%s,%s,%s)", it)

    flash("Quotation saved.", "success")
    saved_q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    if saved_q:
        # Build PDF whenever status is Pending or Approved — customer will receive it
        pdf_bytes = None
        customer_email = (saved_q.get("customer_email") or "").strip()
        if saved_q.get("status") in ("Pending", "Approved") and customer_email:
            try:
                saved_items = query("SELECT * FROM quotation_items WHERE quotation_id=%s ORDER BY line_no", (qid,))
                pdf_bytes   = build_quotation_pdf(dict(saved_q), [dict(i) for i in saved_items],
                                                  sig_bytes=_load_default_sig())
            except Exception:
                pdf_bytes = None
            customer_name = (saved_q.get("customer_name") or "").strip()
            if pdf_bytes:
                flash(f"📎 Quotation PDF sent to {customer_name} &lt;{customer_email}&gt;.", "info")
            else:
                flash(f"⚠️ PDF generation failed — quotation was NOT emailed to {customer_name} ({customer_email}).", "warning")
        notify_quotation(dict(saved_q), action="created" if _is_new else "updated",
                         pdf_bytes=pdf_bytes)
        if saved_q.get("status") == "Approved":
            _maybe_create_approval_task(qid, dict(saved_q))
    return redirect(url_for("quotations_view", qid=qid))


def _maybe_create_approval_task(qid: str, q_rec: dict):
    """Auto-create a job execution task when a quotation is approved.
    Safe to call multiple times — skips if a task linked to this quotation already exists.
    """
    existing = query_one("SELECT id FROM tasks WHERE linked_quotation_id=%s LIMIT 1", (qid,))
    if existing:
        return  # already has a task, don't duplicate

    qno    = q_rec.get("quotation_no", "—")
    client = q_rec.get("customer_name", "—")
    phone  = q_rec.get("customer_phone") or "—"
    addr   = q_rec.get("customer_address") or "—"
    amount = q_rec.get("total_amount") or 0
    title_ = (q_rec.get("title") or "").strip()

    # Build system description from line items (same logic as /api/quotation/.../being-for)
    items = query(
        "SELECT description, qty FROM quotation_items "
        "WHERE quotation_id=%s AND description<>'' ORDER BY line_no", (qid,))
    _KW = [
        ("inverter",          ["inverter", "ups ", "u.p.s"]),
        ("battery",           ["battery", "batteries", "lithium", "lifepo4", "gel battery", "agm"]),
        ("solar panel",       ["solar panel", "pv module", "pv panel", "solar module", " panel"]),
        ("charge controller", ["charge controller", "mppt", "pwm controller"]),
        ("transfer switch",   ["transfer switch", "ats", "changeover"]),
    ]
    found = {}
    for row in (items or []):
        dl = (row["description"] or "").lower()
        qty_str = f"{row['qty']:g}× " if (row.get("qty") or 1) != 1 else ""
        for group, kws in _KW:
            if group in found:
                continue
            if any(k in dl for k in kws):
                short = row["description"].strip()
                found[group] = f"{qty_str}{short[:57]}{'…' if len(short)>57 else ''}"
    priority_order = ["inverter", "battery", "solar panel", "charge controller", "transfer switch"]
    spec_parts = [found[k] for k in priority_order if k in found]

    if title_ and title_.lower() not in ("quotation", "quote") and spec_parts:
        system_desc = f"Supply and installation of {title_} — {', '.join(spec_parts)}"
    elif title_ and title_.lower() not in ("quotation", "quote"):
        system_desc = f"Supply and installation of {title_}"
    elif spec_parts:
        system_desc = f"Supply and installation of {', '.join(spec_parts)}"
    else:
        system_desc = f"Execute job for {client}"

    notes = (f"Customer: {client}\n"
             f"Phone: {phone}\n"
             f"Address: {addr}\n"
             f"Quotation: {qno}\n"
             f"Amount: UGX {amount:,.0f}\n\n"
             f"{system_desc}")

    # Assign task to executor(s) — fall back to Both if none set yet
    exec_rows  = query("SELECT executor_name FROM job_executions WHERE quotation_id=%s", (qid,))
    exec_names = [r["executor_name"] for r in exec_rows if (r.get("executor_name") or "").strip()]

    if len(exec_names) == 1:
        assigned_to = exec_names[0]
    elif len(exec_names) > 1:
        assigned_to = "Both"
    else:
        assigned_to = "Both"
        notes += "\n\n⚠️ Executor not yet assigned — please set one on this quotation."

    execute(
        "INSERT INTO tasks (title, description, due_date, priority, status, assigned_to, linked_quotation_id, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (f"Execute: {qno} — {client}", system_desc,
         None, "High", "Pending", assigned_to, qid, notes))

    new_t = query_one("SELECT * FROM tasks ORDER BY id DESC LIMIT 1")
    if new_t:
        notify_task(dict(new_t), action="created")
    flash(f'✅ Task created for <strong>{qno}</strong> — assigned to {assigned_to}.', "info")


@app.route("/quotations/<qid>/pdf")
@login_required
def quotations_pdf(qid):
    q     = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    items = query("SELECT * FROM quotation_items WHERE quotation_id=%s ORDER BY line_no", (qid,))
    pdf   = build_quotation_pdf(dict(q), [dict(i) for i in items], sig_bytes=_load_default_sig())
    return send_file(io.BytesIO(pdf), download_name=f"{q['quotation_no']}.pdf",
                     as_attachment=True, mimetype="application/pdf")


@app.route("/quotations/<qid>/status", methods=["POST"])
@login_required
def quotations_status(qid):
    status = request.form["status"]
    execute("UPDATE quotations SET status=%s, updated_at=NOW() WHERE id=%s", (status, qid))
    if status == "Completed":
        maint_url = url_for("maintenance_new", qid=qid)
        flash(f'Job marked Completed. <a href="{maint_url}" class="alert-link">Schedule the warranty check</a> now.', "warning")
    else:
        flash(f"Status updated to {status}.", "success")
    q_rec = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
    if q_rec:
        # Build PDF when moving to Pending or Approved — customer gets it
        pdf_bytes = None
        customer_email = (q_rec.get("customer_email") or "").strip()
        if status in ("Pending", "Approved") and customer_email:
            try:
                q_items   = query("SELECT * FROM quotation_items WHERE quotation_id=%s ORDER BY line_no", (qid,))
                pdf_bytes = build_quotation_pdf(dict(q_rec), [dict(i) for i in q_items],
                                                sig_bytes=_load_default_sig())
            except Exception:
                pdf_bytes = None
            customer_name = (q_rec.get("customer_name") or "").strip()
            if pdf_bytes:
                flash(f"📎 Quotation PDF sent to {customer_name} &lt;{customer_email}&gt;.", "info")
            else:
                flash(f"⚠️ PDF generation failed — quotation was NOT emailed to {customer_name} ({customer_email}).", "warning")
        notify_quotation_status(dict(q_rec), new_status=status, pdf_bytes=pdf_bytes)
        if status == "Approved":
            _maybe_create_approval_task(qid, dict(q_rec))
    return redirect(url_for("quotations_view", qid=qid))


# ── Payment recording ─────────────────────────────────────────────────────────
@app.route("/quotations/<qid>/payments/add", methods=["POST"])
@login_required
def payments_add(qid):
    execute("INSERT INTO payments (quotation_id, date, amount, method, notes) VALUES (%s,%s,%s,%s,%s)",
            (qid, request.form["date"], float(request.form["amount"]),
             request.form.get("method","Cash"), request.form.get("notes","")))
    flash("Payment recorded.", "success")
    return redirect(url_for("quotations_view", qid=qid))


@app.route("/payments/<int:pid>/delete", methods=["POST"])
@login_required
def payments_delete(pid):
    row = query_one("SELECT quotation_id FROM payments WHERE id=%s", (pid,))
    execute("DELETE FROM payments WHERE id=%s", (pid,))
    return redirect(url_for("quotations_view", qid=row["quotation_id"]))


# ── Job execution recording ───────────────────────────────────────────────────
@app.route("/quotations/<qid>/executions/add", methods=["POST"])
@login_required
def executions_add(qid):
    name = (request.form.get("executor_name") or "").strip()
    if not name:
        flash("Executor name is required.", "warning")
        return redirect(url_for("quotations_view", qid=qid))
    execute(
        "INSERT INTO job_executions (quotation_id, executor_name, executor_payment, execution_date, notes) "
        "VALUES (%s,%s,%s,%s,%s)",
        (qid, name,
         float(request.form.get("executor_payment", 0) or 0),
         request.form.get("execution_date") or None,
         request.form.get("notes", ""))
    )
    flash(f"Executor {name} added.", "success")
    return redirect(url_for("quotations_view", qid=qid))


@app.route("/quotations/executions/<eid>/delete", methods=["POST"])
@login_required
def executions_delete(eid):
    row = query_one("SELECT quotation_id FROM job_executions WHERE id=%s", (eid,))
    if row:
        execute("DELETE FROM job_executions WHERE id=%s", (eid,))
        flash("Executor removed.", "success")
        return redirect(url_for("quotations_view", qid=row["quotation_id"]))
    abort(404)


# ── Receipts ──────────────────────────────────────────────────────────────────
@app.route("/receipts")
@login_required
def receipts_list():
    rows = query(
        "SELECT r.id, r.receipt_no, r.customer_name, r.amount_fig, r.amount_paid, r.balance, r.date, "
        "q.quotation_no FROM receipts r LEFT JOIN quotations q ON q.id=r.quotation_id "
        "ORDER BY r.created_at DESC")
    return render_template("receipt/list.html", receipts=rows)


@app.route("/receipts/new", methods=["GET", "POST"])
@login_required
def receipts_new():
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone, customer_email, total_amount FROM quotations ORDER BY date DESC LIMIT 100")

    # Build a map of previously paid amounts per quotation
    prev_paid_rows = query(
        "SELECT quotation_id, COALESCE(SUM(amount_paid),0) AS total_paid "
        "FROM receipts WHERE quotation_id IS NOT NULL GROUP BY quotation_id")
    prev_paid = {str(row["quotation_id"]): float(row["total_paid"]) for row in (prev_paid_rows or [])}

    # Build a map of last being_for per quotation (for consistency across installments)
    being_for_rows = query(
        "SELECT DISTINCT ON (quotation_id) quotation_id, being_for "
        "FROM receipts WHERE quotation_id IS NOT NULL AND being_for <> '' "
        "ORDER BY quotation_id, date DESC")
    being_for_map = {str(row["quotation_id"]): row["being_for"] for row in (being_for_rows or [])}

    if request.method == "POST":
        f    = request.form
        rid  = str(uuid.uuid4())
        # Auto-generate next receipt number
        yr   = date.today().year
        last = query_one(
            "SELECT receipt_no FROM receipts WHERE receipt_no LIKE %s ORDER BY receipt_no DESC LIMIT 1",
            (f"RCT-{yr}-%",))
        if last:
            try:
                last_num = int(last["receipt_no"].rsplit("-", 1)[-1])
                rno = f"RCT-{yr}-{last_num+1:03d}"
            except Exception:
                rno = f"RCT-{yr}-001"
        else:
            rno = f"RCT-{yr}-001"
        # Allow manual override if user typed one
        manual_rno = f.get("receipt_no", "").strip()
        if manual_rno and manual_rno != f"RCT-{yr}-???":
            rno = manual_rno

        fig  = float(f.get("amount_fig", 0))
        paid = float(f.get("amount_paid", 0))
        qid  = f.get("quotation_id") or None
        mid  = f.get("maintenance_id") or None

        # Balance = invoice total - all prior payments on this quotation - this payment
        already_paid = 0.0
        if qid:
            row = query_one(
                "SELECT COALESCE(SUM(amount_paid),0) AS total FROM receipts WHERE quotation_id=%s",
                (qid,))
            already_paid = float(row["total"]) if row else 0.0
        balance = fig - already_paid - paid

        execute("""INSERT INTO receipts
            (id,receipt_no,date,customer_name,customer_phone,customer_email,
             customer_address,being_for,amount_fig,amount_paid,balance,cheque_no,
             issued_name,received_name,collected_by,quotation_id,maintenance_id,payment_method)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, rno, f.get("date") or date.today().isoformat(),
             f["customer_name"], f.get("customer_phone",""), f.get("customer_email",""),
             f.get("customer_address",""), f.get("being_for",""),
             fig, paid, balance, f.get("cheque_no",""),
             f.get("issued_name",""), f.get("received_name",""),
             f.get("collected_by","Hillary"), qid, mid,
             f.get("payment_method","Cash")))
        flash("Receipt saved.", "success")
        new_r = query_one("SELECT * FROM receipts WHERE id=%s", (rid,))
        if new_r:
            r_dict         = dict(new_r)
            customer_email = (r_dict.get("customer_email") or "").strip()
            customer_name  = (r_dict.get("customer_name") or "").strip()
            pdf_bytes      = None
            if customer_email:
                try:
                    pdf_bytes = build_receipt_pdf(r_dict, sig_issued_bytes=_load_default_sig())
                except Exception:
                    pdf_bytes = None
            notify_receipt(r_dict, pdf_bytes=pdf_bytes)
            if customer_email:
                if pdf_bytes:
                    flash(f"📎 Receipt PDF sent to {customer_name} &lt;{customer_email}&gt;.", "info")
                else:
                    flash(f"⚠️ PDF generation failed — receipt was NOT emailed to {customer_name} ({customer_email}).", "warning")
        return redirect(url_for("receipts_view", rid=rid))

    # Auto-generate next receipt number for pre-fill
    yr = date.today().year
    last = query_one(
        "SELECT receipt_no FROM receipts WHERE receipt_no LIKE %s ORDER BY receipt_no DESC LIMIT 1",
        (f"RCT-{yr}-%",))
    if last:
        try:
            last_num = int(last["receipt_no"].rsplit("-", 1)[-1])
            next_rno = f"RCT-{yr}-{last_num+1:03d}"
        except Exception:
            next_rno = f"RCT-{yr}-001"
    else:
        next_rno = f"RCT-{yr}-001"

    prefill_qid = request.args.get("qid")
    prefill_mid = request.args.get("mid")
    prefill_maint = None
    if prefill_mid:
        prefill_maint = query_one("SELECT * FROM maintenance_records WHERE id=%s", (prefill_mid,))
    return render_template("receipt/form.html", r=None, quotations=quotations,
                           prev_paid=prev_paid,
                           being_for_map=being_for_map,
                           next_rno=next_rno,
                           today=date.today().isoformat(),
                           prefill_qid=prefill_qid, prefill_mid=prefill_mid, prefill_maint=prefill_maint)


@app.route("/receipts/<rid>")
@login_required
def receipts_view(rid):
    r = query_one(
        "SELECT r.*, q.quotation_no FROM receipts r "
        "LEFT JOIN quotations q ON q.id=r.quotation_id WHERE r.id=%s", (rid,))
    if not r:
        abort(404)
    return render_template("receipt/view.html", r=r)


@app.route("/receipts/<rid>/edit", methods=["GET", "POST"])
@login_required
def receipts_edit(rid):
    r = query_one("SELECT * FROM receipts WHERE id=%s", (rid,))
    if not r:
        abort(404)
    if request.method == "POST":
        f    = request.form
        fig  = float(f.get("amount_fig", 0))
        paid = float(f.get("amount_paid", 0))
        qid  = f.get("quotation_id") or None
        execute("""UPDATE receipts SET
            receipt_no=%s, date=%s, customer_name=%s, customer_phone=%s,
            customer_email=%s, customer_address=%s, being_for=%s,
            amount_fig=%s, amount_paid=%s, balance=%s, cheque_no=%s,
            issued_name=%s, received_name=%s, collected_by=%s, quotation_id=%s,
            payment_method=%s
            WHERE id=%s""",
            (f.get("receipt_no","").strip() or r["receipt_no"], f.get("date") or date.today().isoformat(),
             f["customer_name"], f.get("customer_phone",""), f.get("customer_email",""),
             f.get("customer_address",""), f.get("being_for",""),
             fig, paid, fig - paid, f.get("cheque_no",""),
             f.get("issued_name",""), f.get("received_name",""),
             f.get("collected_by","Hillary"), qid,
             f.get("payment_method","Cash"), rid))
        flash("Receipt updated.", "success")
        updated_r = query_one("SELECT * FROM receipts WHERE id=%s", (rid,))
        if updated_r:
            r_dict         = dict(updated_r)
            customer_email = (r_dict.get("customer_email") or "").strip()
            customer_name  = (r_dict.get("customer_name") or "").strip()
            pdf_bytes      = None
            if customer_email:
                try:
                    pdf_bytes = build_receipt_pdf(r_dict, sig_issued_bytes=_load_default_sig())
                except Exception:
                    pdf_bytes = None
            notify_receipt(r_dict, pdf_bytes=pdf_bytes)
            if customer_email:
                if pdf_bytes:
                    flash(f"📎 Receipt PDF sent to {customer_name} &lt;{customer_email}&gt;.", "info")
                else:
                    flash(f"⚠️ PDF generation failed — receipt was NOT emailed to {customer_name} ({customer_email}).", "warning")
        return redirect(url_for("receipts_view", rid=rid))
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone, customer_email, total_amount FROM quotations ORDER BY date DESC LIMIT 100")
    return render_template("receipt/form.html", r=r, quotations=quotations, prefill_qid=None)


@app.route("/receipts/<rid>/delete", methods=["POST"])
@login_required
def receipts_delete(rid):
    execute("DELETE FROM receipts WHERE id=%s", (rid,))
    flash("Receipt deleted.", "success")
    return redirect(url_for("receipts_list"))


@app.route("/receipts/<rid>/pdf")
@login_required
def receipts_pdf(rid):
    r   = query_one("SELECT * FROM receipts WHERE id=%s", (rid,))
    pdf = build_receipt_pdf(dict(r), sig_issued_bytes=_load_default_sig())
    return send_file(io.BytesIO(pdf), download_name=f"{r['receipt_no']}.pdf",
                     as_attachment=True, mimetype="application/pdf")


# ── Maintenance ───────────────────────────────────────────────────────────────
@app.route("/maintenance")
@login_required
def maintenance_list():
    status = request.args.get("status","")
    sql    = "SELECT m.*, q.quotation_no FROM maintenance_records m LEFT JOIN quotations q ON q.id=m.linked_quotation_id WHERE 1=1"
    params = []
    if status:
        sql += " AND m.status=%s"; params.append(status)
    sql += " ORDER BY m.created_at DESC"
    rows = query(sql, params)
    return render_template("maintenance/list.html", records=rows, status=status)


@app.route("/maintenance/new", methods=["GET","POST"])
@login_required
def maintenance_new():
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone FROM quotations ORDER BY date DESC")
    if request.method == "POST":
        f  = request.form
        execute("""INSERT INTO maintenance_records
            (linked_quotation_id,client_name,client_phone,visit_date,type,
             problem,parts_used,parts_cost,labour_fee,paid_by,h_ratio,d_ratio,
             executor_name,executor_payment,status,notes,cancellation_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f.get("linked_quotation_id") or None,
             f["client_name"], f.get("client_phone",""),
             f.get("visit_date") or date.today().isoformat(),
             f.get("type","Paid"), f.get("problem",""), f.get("parts_used",""),
             float(f.get("parts_cost",0)), float(f.get("labour_fee",0)),
             f.get("paid_by","Hillary"),
             int(f.get("h_ratio",100)), int(f.get("d_ratio",0)),
             f.get("executor_name",""), float(f.get("executor_payment",0)),
             f.get("status","Open"), f.get("notes",""),
             f.get("cancellation_reason","")))
        flash("Maintenance record saved.", "success")
        new_rec = query_one("SELECT * FROM maintenance_records ORDER BY created_at DESC LIMIT 1")
        if new_rec:
            notify_maintenance(new_rec, action="created")
        return redirect(url_for("maintenance_list"))
    prefill_qid = request.args.get("qid")
    return render_template("maintenance/form.html", r=None, quotations=quotations, prefill_qid=prefill_qid)


@app.route("/maintenance/<int:mid>")
@login_required
def maintenance_view(mid):
    r = query_one(
        "SELECT m.*, q.quotation_no FROM maintenance_records m "
        "LEFT JOIN quotations q ON q.id=m.linked_quotation_id WHERE m.id=%s", (mid,))
    if not r:
        abort(404)
    receipts = query("SELECT * FROM receipts WHERE maintenance_id=%s ORDER BY date", (mid,))
    # Financial summary
    total_cost        = float(r["parts_cost"] or 0) + float(r["labour_fee"] or 0)
    h_ratio           = int(r["h_ratio"] or 100)
    d_ratio           = int(r["d_ratio"] or 0)
    revenue           = sum(float(rec["amount_paid"]) for rec in receipts)
    hillary_collected = sum(float(rec["amount_paid"]) for rec in receipts if rec.get("collected_by") == "Hillary")
    dennis_collected  = sum(float(rec["amount_paid"]) for rec in receipts if rec.get("collected_by") == "Dennis")
    paid_by           = r.get("paid_by") or "Hillary"
    hillary_spend     = total_cost if paid_by == "Hillary" else 0.0
    dennis_spend      = total_cost if paid_by == "Dennis"  else 0.0
    profit            = revenue - total_cost
    hillary_total_due = hillary_spend + profit * h_ratio / 100
    dennis_total_due  = dennis_spend  + profit * d_ratio / 100
    hillary_remaining = hillary_total_due - hillary_collected
    dennis_remaining  = dennis_total_due  - dennis_collected
    fin = dict(
        total_cost=total_cost, revenue=revenue, profit=profit,
        h_ratio=h_ratio, d_ratio=d_ratio,
        hillary_spend=hillary_spend, dennis_spend=dennis_spend,
        hillary_total_due=hillary_total_due, dennis_total_due=dennis_total_due,
        hillary_collected=hillary_collected, dennis_collected=dennis_collected,
        hillary_remaining=hillary_remaining, dennis_remaining=dennis_remaining,
    )
    return render_template("maintenance/view.html", r=r, receipts=receipts, fin=fin)


@app.route("/maintenance/<int:mid>/edit", methods=["GET","POST"])
@login_required
def maintenance_edit(mid):
    r = query_one("SELECT * FROM maintenance_records WHERE id=%s", (mid,))
    if not r:
        abort(404)
    if request.method == "POST":
        f = request.form
        execute("""UPDATE maintenance_records SET
            linked_quotation_id=%s,client_name=%s,client_phone=%s,visit_date=%s,
            type=%s,problem=%s,parts_used=%s,parts_cost=%s,labour_fee=%s,
            paid_by=%s,h_ratio=%s,d_ratio=%s,executor_name=%s,
            executor_payment=%s,status=%s,notes=%s,cancellation_reason=%s WHERE id=%s""",
            (f.get("linked_quotation_id") or None,
             f["client_name"],f.get("client_phone",""),f.get("visit_date"),
             f.get("type","Paid"),f.get("problem",""),f.get("parts_used",""),
             float(f.get("parts_cost",0)),float(f.get("labour_fee",0)),
             f.get("paid_by","Hillary"),
             int(f.get("h_ratio",100)),int(f.get("d_ratio",0)),
             f.get("executor_name",""),float(f.get("executor_payment",0)),
             f.get("status","Open"),f.get("notes",""),
             f.get("cancellation_reason",""),mid))
        flash("Record updated.","success")
        updated_rec = query_one("SELECT * FROM maintenance_records WHERE id=%s", (mid,))
        if updated_rec:
            notify_maintenance(updated_rec, action="updated")
        return redirect(url_for("maintenance_view", mid=mid))
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone FROM quotations ORDER BY date DESC")
    return render_template("maintenance/form.html", r=r, quotations=quotations, prefill_qid=None)


# ── Catalog ───────────────────────────────────────────────────────────────────
@app.route("/catalog")
@login_required
def catalog_list():
    cat    = request.args.get("cat","")
    search = request.args.get("q","")
    sql    = "SELECT * FROM catalog_items WHERE 1=1"
    params = []
    if cat:
        sql += " AND category=%s"; params.append(cat)
    if search:
        sql += " AND (name ILIKE %s OR spec ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql  += " ORDER BY category, name"
    rows  = query(sql, params)
    cats  = [r["category"] for r in query("SELECT DISTINCT category FROM catalog_items ORDER BY category")]
    return render_template("catalog/list.html", items=rows, categories=cats, cat=cat, search=search)


@app.route("/catalog/new", methods=["GET","POST"])
@app.route("/catalog/<item_id>/edit", methods=["GET","POST"])
@login_required
def catalog_edit(item_id=None):
    item = query_one("SELECT * FROM catalog_items WHERE id=%s", (item_id,)) if item_id else None
    if request.method == "POST":
        f       = request.form
        iid     = item_id or f.get("id") or str(uuid.uuid4())[:8].upper()
        cat     = f["category"]

        # Build spec_data from category-specific fields
        spec_data = {}
        if cat == "Solar Panel":
            spec_data = {
                "wp":   float(f.get("spec_wp") or 0),
                "voc":  float(f.get("spec_voc") or 0),
                "vmpp": float(f.get("spec_vmpp") or 0),
                "isc":  float(f.get("spec_isc") or 0),
                "impp": float(f.get("spec_impp") or 0),
            }
        elif cat == "Inverter":
            spec_data = {
                "controller_type":                f.get("spec_controller_type", "MPPT"),
                "battery_voltage":                float(f.get("spec_battery_voltage") or 0),
                "inverter_kw":                    float(f.get("spec_inverter_kw") or 0),
                "mppt_min_v":                     float(f.get("spec_mppt_min_v") or 0),
                "mppt_max_v":                     float(f.get("spec_mppt_max_v") or 0),
                "max_oc_v":                       float(f.get("spec_max_oc_v") or 0),
                "mppt_trackers":                  int(f.get("spec_mppt_trackers") or 1),
                "max_charge_a":                   float(f.get("spec_max_charge_a") or 0),
                "max_pv_power_per_tracker":       float(f.get("spec_max_pv_power_per_tracker") or 0),
                "max_input_current_per_tracker":  float(f.get("spec_max_input_current_per_tracker") or 0),
                "max_isc_per_tracker":            float(f.get("spec_max_isc_per_tracker") or 0),
            }
        elif cat == "Charge Controller":
            spec_data = {
                "controller_type": f.get("spec_controller_type", "MPPT"),
                "battery_voltage": float(f.get("spec_battery_voltage") or 0),
                "max_charge_a":    float(f.get("spec_max_charge_a") or 0),
                "mppt_min_v":      float(f.get("spec_mppt_min_v") or 0),
                "mppt_max_v":      float(f.get("spec_mppt_max_v") or 0),
                "max_oc_v":        float(f.get("spec_max_oc_v") or 0),
            }
        elif cat == "Battery":
            spec_data = {
                "ah":              float(f.get("spec_ah") or 0),
                "voltage":         float(f.get("spec_voltage") or 0),
                "chemistry":       f.get("spec_chemistry", ""),
                "dod_rated":       float(f.get("spec_dod_rated") or 0.8),
                "is_complete_bank": f.get("spec_is_complete_bank") == "1",
            }

        execute("""INSERT INTO catalog_items
                   (id,category,name,spec,uom,buy_price,sell_price,supplier_id,notes,spec_data)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                   category=EXCLUDED.category, name=EXCLUDED.name, spec=EXCLUDED.spec,
                   uom=EXCLUDED.uom, buy_price=EXCLUDED.buy_price,
                   sell_price=EXCLUDED.sell_price, supplier_id=EXCLUDED.supplier_id,
                   notes=EXCLUDED.notes, spec_data=EXCLUDED.spec_data""",
                (iid, cat, f["name"], f.get("spec",""), f.get("uom","pc"),
                 int(f.get("buy_price",0)), int(f.get("sell_price",0)),
                 f.get("supplier_id",""), f.get("notes",""), json.dumps(spec_data)))
        flash("Item saved.", "success")
        return redirect(url_for("catalog_list"))

    categories = ["Battery","Inverter","Solar Panel","Charge Controller","Cable","Accessory","Service"]
    suppliers  = query("SELECT id, name FROM service_providers ORDER BY name")
    # Parse spec_data so the template can access it as a dict
    if item and item.get("spec_data"):
        sd = item["spec_data"]
        item = dict(item)
        item["spec_data"] = sd if isinstance(sd, dict) else json.loads(sd)
    elif item:
        item = dict(item)
        item["spec_data"] = {}
    return render_template("catalog/form.html", item=item, categories=categories, suppliers=suppliers)


@app.route("/catalog/<item_id>/delete", methods=["POST"])
@login_required
def catalog_delete(item_id):
    execute("DELETE FROM catalog_items WHERE id=%s", (item_id,))
    flash("Item deleted.","success")
    return redirect(url_for("catalog_list"))


# ── Suppliers ─────────────────────────────────────────────────────────────────
@app.route("/suppliers")
@login_required
def suppliers_list():
    rows = query("SELECT * FROM service_providers ORDER BY name")
    return render_template("suppliers/list.html", suppliers=rows)


@app.route("/suppliers/new", methods=["GET","POST"])
@app.route("/suppliers/<sid>/edit", methods=["GET","POST"])
@login_required
def suppliers_edit(sid=None):
    supplier = query_one("SELECT * FROM service_providers WHERE id=%s", (sid,)) if sid else None
    if request.method == "POST":
        f   = request.form
        pid = sid or f.get("id") or f"SUP-{str(uuid.uuid4())[:6].upper()}"
        execute("""INSERT INTO service_providers (id,name,contact_person,phone,email,location,categories,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
            name=EXCLUDED.name,contact_person=EXCLUDED.contact_person,phone=EXCLUDED.phone,
            email=EXCLUDED.email,location=EXCLUDED.location,categories=EXCLUDED.categories,
            notes=EXCLUDED.notes""",
            (pid,f["name"],f.get("contact_person",""),f.get("phone",""),
             f.get("email",""),f.get("location",""),f.get("categories",""),f.get("notes","")))
        flash("Supplier saved.","success")
        return redirect(url_for("suppliers_list"))
    return render_template("suppliers/form.html", supplier=supplier)


@app.route("/suppliers/<sid>/delete", methods=["POST"])
@login_required
def suppliers_delete(sid):
    execute("DELETE FROM service_providers WHERE id=%s", (sid,))
    flash("Supplier deleted.","success")
    return redirect(url_for("suppliers_list"))


# ── Balancing helpers ─────────────────────────────────────────────────────────
def _compute_balancing(jid):
    """Compute all financial figures for one balancing job."""
    job = query_one("SELECT * FROM balancing_jobs WHERE id=%s", (jid,))
    if not job:
        return None
    spend_lines  = query("SELECT * FROM balancing_spend_lines WHERE balancing_job_id=%s ORDER BY created_at", (jid,))
    settlements  = query("SELECT * FROM balancing_settlements WHERE balancing_job_id=%s ORDER BY date DESC", (jid,))
    # Receipts are the single source of truth for customer payments
    receipts = query(
        "SELECT * FROM receipts WHERE quotation_id=%s ORDER BY date DESC",
        (job["linked_quotation_id"],)
    ) if job.get("linked_quotation_id") else []

    quoted       = float(job["quoted"] or 0)
    h_ratio      = int(job["h_ratio"] or 45)
    d_ratio      = int(job["d_ratio"] or 55)

    total_costs   = sum(float(s["amount"]) for s in spend_lines)
    dennis_spend  = sum(float(s["amount"]) for s in spend_lines if s["paid_by"] == "Dennis")
    hillary_spend = sum(float(s["amount"]) for s in spend_lines if s["paid_by"] == "Hillary")

    profit              = quoted - total_costs
    hillary_profit_share = profit * h_ratio / 100
    dennis_profit_share  = profit * d_ratio / 100
    hillary_total_due   = hillary_spend + hillary_profit_share
    dennis_total_due    = dennis_spend  + dennis_profit_share

    hillary_collected = sum(float(r["amount_paid"]) for r in receipts if r.get("collected_by") == "Hillary")
    dennis_collected  = sum(float(r["amount_paid"]) for r in receipts if r.get("collected_by") == "Dennis")
    total_collected   = hillary_collected + dennis_collected
    # Settlements split by direction
    hillary_to_dennis = sum(float(s["amount"]) for s in settlements if (s.get("from_person") or "Hillary") == "Hillary")
    dennis_to_hillary = sum(float(s["amount"]) for s in settlements if s.get("from_person") == "Dennis")
    total_settled     = hillary_to_dennis + dennis_to_hillary

    # Symmetric remaining formula:
    # remaining = own_due - own_customer_collected - received_from_other + paid_to_other
    dennis_remaining  = dennis_total_due  - dennis_collected  - hillary_to_dennis + dennis_to_hillary
    hillary_remaining = hillary_total_due - hillary_collected - dennis_to_hillary  + hillary_to_dennis

    warranty_cost = 0.0

    # Computed status — no manual picking needed
    if dennis_remaining <= 0 and hillary_remaining <= 0:
        computed_status = "Settled"
    elif total_collected > 0 or total_settled > 0:
        computed_status = "In Progress"
    else:
        computed_status = "Open"

    fin = dict(
        quoted=quoted, total_costs=total_costs,
        dennis_spend=dennis_spend, hillary_spend=hillary_spend,
        profit=profit, h_ratio=h_ratio, d_ratio=d_ratio,
        hillary_profit_share=hillary_profit_share,
        dennis_profit_share=dennis_profit_share,
        hillary_total_due=hillary_total_due,
        dennis_total_due=dennis_total_due,
        hillary_collected=hillary_collected,
        dennis_collected=dennis_collected,
        total_collected=total_collected,
        hillary_to_dennis=hillary_to_dennis,
        dennis_to_hillary=dennis_to_hillary,
        total_settled=total_settled,
        dennis_remaining=dennis_remaining,
        hillary_remaining=hillary_remaining,
        warranty_cost=warranty_cost,
        true_profit=profit - warranty_cost,
        computed_status=computed_status,
    )
    return job, spend_lines, receipts, settlements, fin


def _balancing_list_query():
    return query("""
        SELECT j.*,
            COALESCE(sl.total_costs,  0) AS total_costs,
            COALESCE(sl.dennis_spend, 0) AS dennis_spend,
            COALESCE(sl.hillary_spend,0) AS hillary_spend,
            COALESCE(cp.hillary_collected,0) AS hillary_collected,
            COALESCE(cp.dennis_collected, 0) AS dennis_collected,
            COALESCE(cp.total_collected,  0) AS total_collected,
            COALESCE(st.hillary_to_dennis,0) AS hillary_to_dennis,
            COALESCE(st.dennis_to_hillary,0) AS dennis_to_hillary
        FROM balancing_jobs j
        LEFT JOIN (
            SELECT balancing_job_id,
                SUM(amount) AS total_costs,
                SUM(CASE WHEN paid_by='Dennis'  THEN amount ELSE 0 END) AS dennis_spend,
                SUM(CASE WHEN paid_by='Hillary' THEN amount ELSE 0 END) AS hillary_spend
            FROM balancing_spend_lines GROUP BY balancing_job_id
        ) sl ON sl.balancing_job_id = j.id
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(SUM(r.amount_paid), 0) AS total_collected,
                COALESCE(SUM(CASE WHEN r.collected_by='Hillary' THEN r.amount_paid ELSE 0 END), 0) AS hillary_collected,
                COALESCE(SUM(CASE WHEN r.collected_by='Dennis'  THEN r.amount_paid ELSE 0 END), 0) AS dennis_collected
            FROM receipts r
            WHERE r.quotation_id = j.linked_quotation_id
        ) cp ON true
        LEFT JOIN (
            SELECT balancing_job_id,
                SUM(CASE WHEN COALESCE(from_person,'Hillary')='Hillary' THEN amount ELSE 0 END) AS hillary_to_dennis,
                SUM(CASE WHEN from_person='Dennis' THEN amount ELSE 0 END) AS dennis_to_hillary
            FROM balancing_settlements GROUP BY balancing_job_id
        ) st ON st.balancing_job_id = j.id
        ORDER BY j.date DESC
    """)


def _enrich_balancing_rows(rows):
    jobs = []
    summary = dict(quoted=0, costs=0, profit=0, h_share=0, d_share=0,
                   hillary_remaining=0, dennis_remaining=0)
    for j in rows:
        j = dict(j)
        quoted  = float(j["quoted"] or 0)
        costs   = float(j["total_costs"])
        profit  = quoted - costs
        hr      = int(j["h_ratio"] or 45)
        dr      = int(j["d_ratio"] or 55)
        h_share = profit * hr / 100
        d_share = profit * dr / 100
        hillary_total_due = float(j["hillary_spend"]) + h_share
        dennis_total_due  = float(j["dennis_spend"])  + d_share
        h2d = float(j.get("hillary_to_dennis") or 0)
        d2h = float(j.get("dennis_to_hillary") or 0)
        hillary_remaining = hillary_total_due - float(j["hillary_collected"]) - d2h + h2d
        dennis_remaining  = dennis_total_due  - float(j["dennis_collected"])  - h2d + d2h
        total_collected   = float(j["hillary_collected"]) + float(j["dennis_collected"])
        total_settled     = h2d + d2h
        if dennis_remaining <= 0 and hillary_remaining <= 0:
            computed_status = "Settled"
        elif total_collected > 0 or total_settled > 0:
            computed_status = "In Progress"
        else:
            computed_status = "Open"
        j.update(profit=profit, h_share=h_share, d_share=d_share,
                 hillary_total_due=hillary_total_due, dennis_total_due=dennis_total_due,
                 hillary_remaining=hillary_remaining, dennis_remaining=dennis_remaining,
                 computed_status=computed_status)
        jobs.append(j)
        summary["quoted"]            += quoted
        summary["costs"]             += costs
        summary["profit"]            += profit
        summary["h_share"]           += h_share
        summary["d_share"]           += d_share
        summary["hillary_remaining"] += hillary_remaining
        summary["dennis_remaining"]  += dennis_remaining
    return jobs, summary


# ── Balancing routes ──────────────────────────────────────────────────────────
@app.route("/balancing")
@login_required
def balancing_list():
    jobs, summary = _enrich_balancing_rows(_balancing_list_query())
    unbalanced = query("""
        SELECT q.id, q.quotation_no, q.customer_name, q.total_amount, q.date,
               je.executor_name, je.execution_date
        FROM quotations q
        LEFT JOIN LATERAL (
            SELECT executor_name, execution_date FROM job_executions
            WHERE quotation_id = q.id ORDER BY execution_date DESC NULLS LAST LIMIT 1
        ) je ON true
        WHERE q.status = 'Completed'
          AND q.id NOT IN (
              SELECT linked_quotation_id FROM balancing_jobs
              WHERE linked_quotation_id IS NOT NULL
          )
        ORDER BY q.date DESC
    """)
    return render_template("balancing/list.html", jobs=jobs, summary=summary, unbalanced=unbalanced)


@app.route("/balancing/report")
@login_required
def balancing_report():
    rows = query("""
        SELECT j.*,
            COALESCE(sl.total_costs,  0) AS total_costs,
            COALESCE(sl.dennis_spend, 0) AS dennis_spend,
            COALESCE(sl.hillary_spend,0) AS hillary_spend,
            COALESCE(cp.hillary_collected,0) AS hillary_collected,
            COALESCE(cp.dennis_collected, 0) AS dennis_collected,
            COALESCE(cp.total_collected,  0) AS total_collected,
            COALESCE(st.hillary_to_dennis,0) AS hillary_to_dennis,
            COALESCE(st.dennis_to_hillary,0) AS dennis_to_hillary
        FROM balancing_jobs j
        LEFT JOIN (
            SELECT balancing_job_id,
                SUM(amount) AS total_costs,
                SUM(CASE WHEN paid_by='Dennis'  THEN amount ELSE 0 END) AS dennis_spend,
                SUM(CASE WHEN paid_by='Hillary' THEN amount ELSE 0 END) AS hillary_spend
            FROM balancing_spend_lines GROUP BY balancing_job_id
        ) sl ON sl.balancing_job_id = j.id
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(SUM(r.amount_paid), 0) AS total_collected,
                COALESCE(SUM(CASE WHEN r.collected_by='Hillary' THEN r.amount_paid ELSE 0 END), 0) AS hillary_collected,
                COALESCE(SUM(CASE WHEN r.collected_by='Dennis'  THEN r.amount_paid ELSE 0 END), 0) AS dennis_collected
            FROM receipts r
            WHERE r.quotation_id = j.linked_quotation_id
        ) cp ON true
        LEFT JOIN (
            SELECT balancing_job_id,
                SUM(CASE WHEN COALESCE(from_person,'Hillary')='Hillary' THEN amount ELSE 0 END) AS hillary_to_dennis,
                SUM(CASE WHEN from_person='Dennis' THEN amount ELSE 0 END) AS dennis_to_hillary
            FROM balancing_settlements GROUP BY balancing_job_id
        ) st ON st.balancing_job_id = j.id
        ORDER BY j.date
    """)
    jobs, grand = _enrich_balancing_rows(rows)
    return render_template("balancing/report.html", jobs=jobs, grand=grand)


@app.route("/balancing/new", methods=["GET","POST"])
@app.route("/balancing/<jid>/edit", methods=["GET","POST"])
@login_required
def balancing_edit(jid=None):
    _is_new = jid is None
    job = query_one("SELECT * FROM balancing_jobs WHERE id=%s", (jid,)) if jid else None
    existing_spend = query(
        "SELECT * FROM balancing_spend_lines WHERE balancing_job_id=%s ORDER BY id", (jid,)
    ) if jid else []

    if request.method == "POST":
        f   = request.form
        jid = jid or str(uuid.uuid4())[:8].upper()
        execute("""
            INSERT INTO balancing_jobs
                (id, job_name, linked_quotation_id, date, quoted, h_ratio, d_ratio, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                job_name=EXCLUDED.job_name,
                linked_quotation_id=EXCLUDED.linked_quotation_id,
                date=EXCLUDED.date, quoted=EXCLUDED.quoted,
                h_ratio=EXCLUDED.h_ratio, d_ratio=EXCLUDED.d_ratio,
                notes=EXCLUDED.notes
        """, (jid, f["job_name"],
              f.get("linked_quotation_id") or None,
              f.get("date") or date.today().isoformat(),
              float(f.get("quoted", 0)),
              int(f.get("h_ratio", 45)),
              int(f.get("d_ratio", 55)),
              f.get("notes", "")))
        # Save spend lines
        execute("DELETE FROM balancing_spend_lines WHERE balancing_job_id=%s", (jid,))
        for desc, paid_by, amt in zip(
            f.getlist("sl_desc[]"), f.getlist("sl_paid_by[]"), f.getlist("sl_amount[]")
        ):
            if desc.strip() and amt.strip():
                execute(
                    "INSERT INTO balancing_spend_lines (balancing_job_id, description, paid_by, amount) "
                    "VALUES (%s,%s,%s,%s)",
                    (jid, desc.strip(), paid_by, float(amt))
                )
        flash("Job saved.", "success")
        saved_job = query_one(
            "SELECT bj.*, q.quotation_no FROM balancing_jobs bj "
            "LEFT JOIN quotations q ON q.id=bj.linked_quotation_id WHERE bj.id=%s", (jid,))
        if saved_job:
            notify_balancing_job(dict(saved_job), action="created" if _is_new else "updated")
        return redirect(url_for("balancing_view", jid=jid))

    # ?qid= prefill for new jobs
    prefill = {}
    if not jid:
        qid = request.args.get("qid")
        if qid:
            q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
            if q:
                execs = query(
                    "SELECT executor_name, executor_payment, execution_date FROM job_executions "
                    "WHERE quotation_id=%s ORDER BY id",
                    (qid,)
                )
                # Guard: no executor recorded — send back to quotation with a clear message
                if not execs:
                    flash(
                        f'No executor recorded for {q["quotation_no"]}. '
                        f'Add an executor first, then come back to balance.',
                        "warning"
                    )
                    return redirect(url_for("quotations_view", qid=qid) + "#job-execution")
                prefill_spend = []
                for exe in (execs or []):
                    pay = float(exe.get("executor_payment") or 0)
                    if pay > 0:
                        name = (exe.get("executor_name") or "Executor").strip()
                        prefill_spend.append({
                            "description": f"{name} labour",
                            "paid_by": name if name in ("Hillary", "Dennis") else "Dennis",
                            "amount": pay,
                        })
                last_exe = execs[-1] if execs else None
                prefill = {
                    "job_name":            f"{q['customer_name']} — {q['quotation_no']}",
                    "quoted":              q["total_amount"],
                    "linked_quotation_id": qid,
                    "date": (last_exe["execution_date"].isoformat()
                             if last_exe and last_exe.get("execution_date") else ""),
                    "spend_lines":         prefill_spend,
                }

    quotations = query("SELECT id, quotation_no, customer_name FROM quotations ORDER BY date DESC LIMIT 100")
    return render_template("balancing/form.html", job=job, quotations=quotations,
                           prefill=prefill, existing_spend=existing_spend)


@app.route("/balancing/<jid>")
@login_required
def balancing_view(jid):
    result = _compute_balancing(jid)
    if not result:
        abort(404)
    job, spend_lines, receipts, settlements, fin = result
    return render_template("balancing/view.html",
                           job=job, spend_lines=spend_lines,
                           receipts=receipts, settlements=settlements, fin=fin)


@app.route("/balancing/<jid>/status", methods=["POST"])
@login_required
def balancing_status(jid):
    execute("UPDATE balancing_jobs SET status=%s WHERE id=%s", (request.form["status"], jid))
    flash("Status updated.", "success")
    return redirect(url_for("balancing_view", jid=jid))


@app.route("/balancing/<jid>/spend/add", methods=["POST"])
@login_required
def balancing_spend_add(jid):
    f = request.form
    execute("INSERT INTO balancing_spend_lines (balancing_job_id, paid_by, description, amount, date) VALUES (%s,%s,%s,%s,%s)",
            (jid, f["paid_by"], f["description"], float(f["amount"]), f.get("date") or None))
    flash("Spend line added.", "success")
    return redirect(url_for("balancing_view", jid=jid))


@app.route("/balancing/<jid>/spend/<int:sid>/delete", methods=["POST"])
@login_required
def balancing_spend_delete(jid, sid):
    execute("DELETE FROM balancing_spend_lines WHERE id=%s AND balancing_job_id=%s", (sid, jid))
    return redirect(url_for("balancing_view", jid=jid))




@app.route("/balancing/<jid>/settlements/add", methods=["POST"])
@login_required
def balancing_settlement_add(jid):
    f           = request.form
    amount      = float(f["amount"])
    from_person = f.get("from_person", "Hillary")
    to_person   = "Dennis" if from_person == "Hillary" else "Hillary"
    notes       = f.get("notes", "")
    execute(
        "INSERT INTO balancing_settlements (balancing_job_id, date, amount, from_person, notes) "
        "VALUES (%s,%s,%s,%s,%s)",
        (jid, f.get("date") or date.today().isoformat(), amount, from_person, notes)
    )
    flash("Settlement recorded.", "success")
    job = query_one("SELECT bj.*, q.quotation_no FROM balancing_jobs bj "
                    "LEFT JOIN quotations q ON q.id=bj.linked_quotation_id WHERE bj.id=%s", (jid,))
    if job:
        notify_settlement(dict(job), amount=amount,
                          from_person=from_person, to_person=to_person, notes=notes)
    return redirect(url_for("balancing_view", jid=jid))


@app.route("/balancing/<jid>/settlements/<int:sid>/delete", methods=["POST"])
@login_required
def balancing_settlement_delete(jid, sid):
    execute("DELETE FROM balancing_settlements WHERE id=%s AND balancing_job_id=%s", (sid, jid))
    return redirect(url_for("balancing_view", jid=jid))


@app.route("/balancing/<jid>/delete", methods=["POST"])
@login_required
def balancing_delete(jid):
    execute("DELETE FROM balancing_jobs WHERE id=%s", (jid,))
    flash("Job deleted.", "success")
    return redirect(url_for("balancing_list"))


# ── Tasks ─────────────────────────────────────────────────────────────────────
@app.route("/tasks")
@login_required
def tasks_list():
    status = request.args.get("status", "")
    sql    = ("SELECT t.*, q.quotation_no FROM tasks t "
              "LEFT JOIN quotations q ON q.id=t.linked_quotation_id WHERE 1=1")
    params = []
    if status == "done":
        sql += " AND t.status='Done'"
    elif status == "cancelled":
        sql += " AND t.status='Cancelled'"
    elif status == "all":
        pass
    else:
        sql += " AND t.status NOT IN ('Done','Cancelled')"
    sql += " ORDER BY t.due_date ASC NULLS LAST, CASE t.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END"
    rows = query(sql, params)
    today = date.today()
    return render_template("tasks/list.html", tasks=rows, status=status, today=today)


@app.route("/tasks/new", methods=["GET","POST"])
@app.route("/tasks/<int:tid>", methods=["GET","POST"])
@login_required
def tasks_edit(tid=None):
    task = query_one("SELECT * FROM tasks WHERE id=%s", (tid,)) if tid else None
    if request.method == "POST":
        f = request.form
        if f.get("status") == "Cancelled" and not f.get("notes","").strip():
            flash("Cancellation reason is required when status is Cancelled.", "danger")
            quotations = query("SELECT id, quotation_no, customer_name FROM quotations ORDER BY date DESC LIMIT 100")
            _default_members = ['Hillary', 'Dennis', 'Both']
            _extra = query("SELECT DISTINCT assigned_to FROM tasks WHERE assigned_to IS NOT NULL AND assigned_to != '' ORDER BY assigned_to")
            team_members = list(dict.fromkeys(_default_members + [r['assigned_to'] for r in _extra if r['assigned_to'] not in _default_members]))
            return render_template("tasks/form.html", task=task or f, quotations=quotations, team_members=team_members)
        if tid:
            execute("""UPDATE tasks SET title=%s, description=%s, due_date=%s,
                priority=%s, status=%s, assigned_to=%s, linked_quotation_id=%s,
                notes=%s, updated_at=NOW() WHERE id=%s""",
                (f["title"], f.get("description",""),
                 f.get("due_date") or None,
                 f.get("priority","Normal"), f.get("status","Pending"),
                 f.get("assigned_to",""), f.get("linked_quotation_id") or None,
                 f.get("notes",""), tid))
        else:
            execute("""INSERT INTO tasks
                (title, description, due_date, priority, status, assigned_to, linked_quotation_id, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (f["title"], f.get("description",""),
                 f.get("due_date") or None,
                 f.get("priority","Normal"), f.get("status","Pending"),
                 f.get("assigned_to",""), f.get("linked_quotation_id") or None,
                 f.get("notes","")))
        flash("Task saved.", "success")
        if tid:
            saved_t = query_one("SELECT * FROM tasks WHERE id=%s", (tid,))
            if saved_t:
                notify_task(dict(saved_t), action="updated")
        else:
            saved_t = query_one("SELECT * FROM tasks ORDER BY id DESC LIMIT 1")
            if saved_t:
                notify_task(dict(saved_t), action="created")
        return redirect(url_for("tasks_list"))
    quotations = query("SELECT id, quotation_no, customer_name FROM quotations ORDER BY date DESC LIMIT 100")
    _default_members = ['Hillary', 'Dennis', 'Both']
    _extra = query("SELECT DISTINCT assigned_to FROM tasks WHERE assigned_to IS NOT NULL AND assigned_to != '' ORDER BY assigned_to")
    team_members = list(dict.fromkeys(_default_members + [r['assigned_to'] for r in _extra if r['assigned_to'] not in _default_members]))
    return render_template("tasks/form.html", task=task, quotations=quotations, team_members=team_members)


@app.route("/tasks/<int:tid>/done", methods=["POST"])
@login_required
def tasks_done(tid):
    execute("UPDATE tasks SET status='Done', updated_at=NOW() WHERE id=%s", (tid,))
    flash("Task marked done.", "success")
    done_t = query_one("SELECT * FROM tasks WHERE id=%s", (tid,))
    if done_t:
        notify_task(dict(done_t), action="completed")
    return redirect(url_for("tasks_list"))


@app.route("/tasks/<int:tid>/delete", methods=["POST"])
@login_required
def tasks_delete(tid):
    execute("DELETE FROM tasks WHERE id=%s", (tid,))
    flash("Task deleted.", "success")
    return redirect(url_for("tasks_list"))


# ── API: template items ────────────────────────────────────────────────────────
@app.route("/api/quotation/<qid>/being-for")
@login_required
def api_quotation_being_for(qid):
    """Return a suggested 'being payment for' string built from the quotation title + line items."""
    q     = query_one("SELECT title FROM quotations WHERE id=%s", (qid,))
    items = query("SELECT description, qty, uom FROM quotation_items WHERE quotation_id=%s AND description<>'' ORDER BY line_no", (qid,))
    if not q:
        return jsonify({"being_for": ""})

    title = (q.get("title") or "").strip()
    # Use title only if it's not the generic default
    title_part = title if title and title.lower() not in ("quotation", "quote", "") else ""

    # Keyword groups — first match per group wins
    _KW = [
        ("inverter",        ["inverter", "ups ", "u.p.s"]),
        ("battery",         ["battery", "batteries", "lithium", "lifepo4", "gel battery", "agm"]),
        ("solar panel",     ["solar panel", "pv module", "pv panel", "solar module", " panel"]),
        ("charge controller",["charge controller", "mppt", "pwm controller"]),
        ("transfer switch", ["transfer switch", "ats", "changeover"]),
    ]

    found = {}
    for row in (items or []):
        desc_lower = (row["description"] or "").lower()
        qty  = row.get("qty") or 1
        qty_str = f"{qty:g}" if qty != 1 else ""
        for group, keywords in _KW:
            if group in found:
                continue
            if any(kw in desc_lower for kw in keywords):
                # Take the raw description, trim to first 60 chars
                short = row["description"].strip()
                if len(short) > 60:
                    short = short[:57].rstrip() + "…"
                found[group] = f"{qty_str}{'× ' if qty_str else ''}{short}"

    # Build specs string from found components (inverter + battery are primary)
    priority = ["inverter", "battery", "solar panel", "charge controller", "transfer switch"]
    spec_parts = [found[k] for k in priority if k in found]

    if title_part and spec_parts:
        being_for = f"Supply and installation of {title_part} — {', '.join(spec_parts)}"
    elif title_part:
        being_for = f"Supply and installation of {title_part}"
    elif spec_parts:
        being_for = f"Supply and installation of {', '.join(spec_parts)}"
    else:
        being_for = ""

    return jsonify({"being_for": being_for})


@app.route("/api/template/<tid>")
@login_required
def api_template(tid):
    items = query(
        "SELECT DISTINCT ON (ti.description) ti.*, ci.sell_price FROM template_items ti "
        "LEFT JOIN catalog_items ci ON ci.id=ti.catalog_item_id "
        "WHERE ti.template_id=%s ORDER BY ti.description, ti.id", (tid,))
    return jsonify([dict(i) for i in items])


# ── Solar Sizing ───────────────────────────────────────────────────────────────
from utils.solar import calc_sizing, build_bom
from utils.solar_pptx import build_proposal

_DEFAULT_APPLIANCES = [
    {"name": "LED Bulb (10W)",       "power_w": 10,  "power_factor": 0.95, "quantity": 6,  "hours_per_day": 6,   "included": True, "daily_wh": 0},
    {"name": "LED TV (55 inch)",     "power_w": 80,  "power_factor": 0.85, "quantity": 1,  "hours_per_day": 5,   "included": True, "daily_wh": 0},
    {"name": "Wi-Fi Router",         "power_w": 12,  "power_factor": 0.85, "quantity": 1,  "hours_per_day": 18,  "included": True, "daily_wh": 0},
    {"name": "Phone Charging",       "power_w": 15,  "power_factor": 0.85, "quantity": 3,  "hours_per_day": 2,   "included": True, "daily_wh": 0},
    {"name": "Laptop",               "power_w": 65,  "power_factor": 0.85, "quantity": 1,  "hours_per_day": 4,   "included": False, "daily_wh": 0},
    {"name": "Refrigerator (150L)",  "load_type": "fridge", "annual_kwh": 200, "peak_w": 300, "power_w": 0, "power_factor": 0.85, "quantity": 1, "hours_per_day": 0, "included": False, "daily_wh": 0},
    {"name": "Water Pump (0.5HP)",   "power_w": 400, "power_factor": 0.85, "quantity": 1,  "hours_per_day": 1,   "included": False, "daily_wh": 0},
]


def _parse_appliances_from_form(f):
    """Extract appliance rows from form POST data."""
    names      = f.getlist("app_name[]")
    load_types = f.getlist("app_load_type[]")
    powers     = f.getlist("app_power_w[]")
    annual_kwhs = f.getlist("app_annual_kwh[]")
    peak_ws    = f.getlist("app_peak_w[]")
    pfs        = f.getlist("app_power_factor[]")
    qtys       = f.getlist("app_qty[]")
    hours      = f.getlist("app_hours[]")
    sentinels  = f.getlist("app_included_sentinel[]")

    # Checkboxes only post when checked; sentinels define total row count
    included_values = f.getlist("app_included[]")
    included_flags  = []
    inc_iter = iter(included_values)
    for _ in sentinels:
        try:
            next(inc_iter)
            included_flags.append(True)
        except StopIteration:
            included_flags.append(False)

    appliances = []
    for i, name in enumerate(names):
        if not name.strip():
            continue
        lt = load_types[i] if i < len(load_types) else 'standard'
        appliances.append({
            "name":          name.strip(),
            "load_type":     lt,
            "power_w":       float(powers[i] or 0) if i < len(powers) else 0,
            "annual_kwh":    float(annual_kwhs[i] or 0) if i < len(annual_kwhs) else 0,
            "peak_w":        float(peak_ws[i] or 0) if i < len(peak_ws) else 0,
            "power_factor":  float(pfs[i] or 1.0) if i < len(pfs) else 1.0,
            "quantity":      int(qtys[i] or 1) if i < len(qtys) else 1,
            "hours_per_day": float(hours[i] or 0) if i < len(hours) else 0,
            "included":      included_flags[i] if i < len(included_flags) else True,
            "daily_wh":      0,
        })
    return appliances


def _params_from_form(f):
    return {
        "system_voltage":     int(f.get("system_voltage", 48)),
        "battery_type":       f.get("battery_type", "Li-ion"),
        "days_autonomy":      int(f.get("days_autonomy", 1)),
        "dod":                float(f.get("dod", 0.80)),
        "inverter_efficiency": float(f.get("inverter_efficiency", 0.90)),
        "cable_efficiency":   float(f.get("cable_efficiency", 0.95)),
        "inverter_idle_w":    float(f.get("inverter_idle_w", 50)),
        "peak_sun_hours":     float(f.get("peak_sun_hours", 5.5)),
        "performance_ratio":  float(f.get("performance_ratio", 0.75)),
        "panel_wp":                          float(f.get("panel_wp", 550)),
        "panel_voc":                         float(f.get("panel_voc", 40.0)),
        "panel_isc":                         float(f.get("panel_isc", 0)),
        "panel_cost":                        float(f.get("panel_cost", 0)),
        "mppt_trackers":                     int(f.get("mppt_trackers", 1)),
        "mppt_min_v":                        float(f.get("mppt_min_v", 0)),
        "mppt_max_v":                        float(f.get("mppt_max_v", 0)),
        "max_oc_v":                          float(f.get("max_oc_v", 0)),
        "max_input_current_per_tracker":     float(f.get("max_input_current_per_tracker", 0)),
        "max_isc_per_tracker":               float(f.get("max_isc_per_tracker", 0)),
        "max_pv_power_per_tracker":          float(f.get("max_pv_power_per_tracker", 0)),
        "battery_ah":         float(f.get("battery_ah", 200)),
        "battery_voltage":    float(f.get("battery_voltage", 12)),
        "battery_cost_each":  float(f.get("battery_cost_each", 0)),
        "inverter_kw":        float(f.get("inverter_kw", 3.5)),
        "inverter_cost":      float(f.get("inverter_cost", 0)),
        "labour_transport":   float(f.get("labour_transport", 750000)),
        "utility_provider":   f.get("utility_provider", "UEDCL"),
        "utility_tariff":     float(f.get("utility_tariff", 897)),
        "tariff_escalation":  float(f.get("tariff_escalation", 4.0)) / 100,  # convert % → decimal
        "battery_is_bank":    f.get("battery_is_bank") == "1",
    }


def _recompute_financials(results, bom_total, params):
    """Patch results dict with financial metrics derived from the true BoM total."""
    maint    = results['maintenance_cost_10yr']
    coo_10yr = bom_total + maint
    ten_yr   = results['annual_yield_kwh'] * 10
    util_t   = params['utility_tariff']
    tariff_e = params['tariff_escalation']  # already decimal (0.04 = 4%)
    if tariff_e > 0:
        ten_yr_grid = sum(results['annual_yield_kwh'] * util_t * ((1 + tariff_e) ** yr) for yr in range(10))
    else:
        ten_yr_grid = ten_yr * util_t
    annual_sav = results['annual_yield_kwh'] * util_t
    results['system_cost']        = round(bom_total, 0)
    results['solar_cost_per_kwh'] = round(coo_10yr / ten_yr, 2) if ten_yr > 0 else 0
    results['yaka_savings_10yr']  = round(ten_yr_grid - coo_10yr, 0)
    results['payback_years']      = round(bom_total / annual_sav, 2) if annual_sav > 0 else 0


def _reconcile_results_with_bom(s, bom_list):
    """Return a results dict where panel/battery counts, array arrangement,
    annual yield and all financials are derived from the *actual* BoM rather
    than the stored engineering recommendation.

    Once a BoM is edited (e.g. 4 panels in one series string instead of the
    auto-recommended 2, or 1 battery instead of 2), the stored calc fields go
    stale. This keeps the on-screen engineering summary, the financial
    appraisal and the PPTX proposal all consistent with what was quoted.
    """
    r = dict(s)
    panel_row = next((b for b in bom_list
                      if 'solar panel' in str(b['description']).lower()
                      and 'mount' not in str(b['description']).lower()), None)
    battery_row = next((b for b in bom_list
                        if str(b['description']).lower().startswith('battery')), None)

    # --- Panels: actual count drives yield + array arrangement ---
    if panel_row:
        actual_panels    = int(float(panel_row['qty']))
        strings_total    = max(1, int(r.get('strings_total') or 1))
        panels_in_series = math.ceil(actual_panels / strings_total)
        trackers         = max(1, int(s.get('mppt_trackers') or 1))
        r['panels_recommended']  = actual_panels
        r['panels_in_series']    = panels_in_series
        r['strings_total']       = strings_total
        r['strings_per_tracker'] = math.ceil(strings_total / trackers)
        r['voltage_override']    = actual_panels > int(r.get('panels_by_energy') or actual_panels)
        # The BoM is a human-approved, valid array → clear the stale string warning
        r['inverter_flag']       = ''
        panel_wp = float(s.get('panel_wp') or 0)
        psh      = float(s.get('peak_sun_hours') or 5.5)
        pr       = float(s.get('performance_ratio') or 0.75)
        r['annual_yield_kwh'] = round(panel_wp * actual_panels * psh * 365 * pr / 1000, 1)

    # --- Batteries: actual count drives the bank arrangement ---
    if battery_row:
        actual_batt = int(float(battery_row['qty']))
        batt_series = max(1, int(r.get('batteries_in_series') or 1))
        r['total_batteries']       = actual_batt
        r['batteries_in_parallel'] = max(1, math.ceil(actual_batt / batt_series))

    # --- Financials from the true BoM total ---
    bom_total = sum(float(b['total']) for b in bom_list)
    if bom_total > 0:
        params = {
            'utility_tariff':    float(s.get('utility_tariff') or 897),
            'tariff_escalation': float(s.get('tariff_escalation') or 0) / 100,  # DB stores %
        }
        r['maintenance_cost_10yr'] = float(r.get('maintenance_cost_10yr') or 0)
        _recompute_financials(r, bom_total, params)
    return r


def _save_sizing(sid, f):
    """Save sizing + appliances, run calculation, store results. Returns sid."""
    sid        = sid or str(uuid.uuid4())
    params     = _params_from_form(f)
    appliances = _parse_appliances_from_form(f)
    results    = calc_sizing(params, appliances)

    # Check if the BoM has been manually locked (user customised it)
    existing     = query("SELECT bom_locked FROM solar_sizings WHERE id=%s", (sid,))
    bom_locked   = bool(existing[0]['bom_locked']) if existing else False

    if bom_locked:
        # Keep existing BoM; derive system_cost from stored rows
        existing_bom = query("SELECT total FROM solar_sizing_bom WHERE sizing_id=%s", (sid,))
        bom_total    = sum(float(r['total']) for r in existing_bom)
        bom_items    = None   # don't rebuild
    else:
        bom_items = build_bom(params, results)
        bom_total = sum(item['total'] for item in bom_items)

    # True system cost = BoM total (includes fixed accessories not in calc_sizing estimate)
    _recompute_financials(results, bom_total, params)

    # tariff_escalation stored as % in DB (not decimal) — convert back for storage
    tariff_esc_pct = params["tariff_escalation"] * 100

    # Upsert solar_sizings
    execute("""
        INSERT INTO solar_sizings (
            id, client_name, client_phone, client_email, client_site,
            utility_provider, utility_tariff, tariff_escalation,
            system_voltage, battery_type, days_autonomy, dod,
            inverter_efficiency, cable_efficiency, inverter_idle_w, peak_sun_hours, performance_ratio,
            panel_wp, panel_voc, panel_isc, panel_cost,
            mppt_trackers, mppt_min_v, mppt_max_v, max_oc_v,
            max_input_current_per_tracker, max_isc_per_tracker, max_pv_power_per_tracker,
            battery_ah, battery_voltage, battery_cost_each, battery_is_bank,
            inverter_kw, inverter_cost, labour_transport,
            total_daily_wh, inverter_idle_wh, peak_load_w, battery_ah_min,
            batteries_in_series, batteries_in_parallel, total_batteries,
            required_wp, panels_by_energy, panels_by_voltage,
            panels_in_series, strings_total, strings_per_tracker,
            panels_recommended, voltage_override, annual_yield_kwh,
            system_cost, maintenance_cost_10yr, solar_cost_per_kwh,
            yaka_savings_10yr, payback_years, inverter_flag, panel_array_flag,
            notes, updated_at
        ) VALUES (
            %s,%s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s, NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            client_name=EXCLUDED.client_name, client_phone=EXCLUDED.client_phone,
            client_email=EXCLUDED.client_email, client_site=EXCLUDED.client_site,
            utility_provider=EXCLUDED.utility_provider, utility_tariff=EXCLUDED.utility_tariff,
            tariff_escalation=EXCLUDED.tariff_escalation,
            system_voltage=EXCLUDED.system_voltage, battery_type=EXCLUDED.battery_type,
            days_autonomy=EXCLUDED.days_autonomy, dod=EXCLUDED.dod,
            inverter_efficiency=EXCLUDED.inverter_efficiency, cable_efficiency=EXCLUDED.cable_efficiency,
            inverter_idle_w=EXCLUDED.inverter_idle_w,
            peak_sun_hours=EXCLUDED.peak_sun_hours, performance_ratio=EXCLUDED.performance_ratio,
            panel_wp=EXCLUDED.panel_wp, panel_voc=EXCLUDED.panel_voc,
            panel_isc=EXCLUDED.panel_isc, panel_cost=EXCLUDED.panel_cost,
            mppt_trackers=EXCLUDED.mppt_trackers,
            mppt_min_v=EXCLUDED.mppt_min_v, mppt_max_v=EXCLUDED.mppt_max_v,
            max_oc_v=EXCLUDED.max_oc_v,
            max_input_current_per_tracker=EXCLUDED.max_input_current_per_tracker,
            max_isc_per_tracker=EXCLUDED.max_isc_per_tracker,
            max_pv_power_per_tracker=EXCLUDED.max_pv_power_per_tracker,
            battery_ah=EXCLUDED.battery_ah, battery_voltage=EXCLUDED.battery_voltage,
            battery_cost_each=EXCLUDED.battery_cost_each, battery_is_bank=EXCLUDED.battery_is_bank,
            inverter_kw=EXCLUDED.inverter_kw, inverter_cost=EXCLUDED.inverter_cost,
            labour_transport=EXCLUDED.labour_transport,
            total_daily_wh=EXCLUDED.total_daily_wh, inverter_idle_wh=EXCLUDED.inverter_idle_wh,
            peak_load_w=EXCLUDED.peak_load_w, battery_ah_min=EXCLUDED.battery_ah_min,
            batteries_in_series=EXCLUDED.batteries_in_series,
            batteries_in_parallel=EXCLUDED.batteries_in_parallel,
            total_batteries=EXCLUDED.total_batteries,
            required_wp=EXCLUDED.required_wp, panels_by_energy=EXCLUDED.panels_by_energy,
            panels_by_voltage=EXCLUDED.panels_by_voltage,
            panels_in_series=EXCLUDED.panels_in_series,
            strings_total=EXCLUDED.strings_total, strings_per_tracker=EXCLUDED.strings_per_tracker,
            panels_recommended=EXCLUDED.panels_recommended,
            voltage_override=EXCLUDED.voltage_override,
            annual_yield_kwh=EXCLUDED.annual_yield_kwh,
            system_cost=EXCLUDED.system_cost, maintenance_cost_10yr=EXCLUDED.maintenance_cost_10yr,
            solar_cost_per_kwh=EXCLUDED.solar_cost_per_kwh,
            yaka_savings_10yr=EXCLUDED.yaka_savings_10yr, payback_years=EXCLUDED.payback_years,
            inverter_flag=EXCLUDED.inverter_flag, panel_array_flag=EXCLUDED.panel_array_flag,
            notes=EXCLUDED.notes, updated_at=NOW()
    """, (
        sid,
        f.get("client_name"), f.get("client_phone",""), f.get("client_email",""), f.get("client_site",""),
        params["utility_provider"], params["utility_tariff"], tariff_esc_pct,
        params["system_voltage"], params["battery_type"], params["days_autonomy"], params["dod"],
        params["inverter_efficiency"], params["cable_efficiency"], params["inverter_idle_w"],
        params["peak_sun_hours"], params["performance_ratio"],
        params["panel_wp"], params["panel_voc"], params["panel_isc"], params["panel_cost"],
        params["mppt_trackers"], params["mppt_min_v"], params["mppt_max_v"], params["max_oc_v"],
        params["max_input_current_per_tracker"], params["max_isc_per_tracker"], params["max_pv_power_per_tracker"],
        params["battery_ah"], params["battery_voltage"], params["battery_cost_each"], params["battery_is_bank"],
        params["inverter_kw"], params["inverter_cost"], params["labour_transport"],
        results["total_daily_wh"], results["inverter_idle_wh"], results["peak_load_w"], results["battery_ah_min"],
        results["batteries_in_series"], results["batteries_in_parallel"], results["total_batteries"],
        results["required_wp"], results["panels_by_energy"], results["panels_by_voltage"],
        results["panels_in_series"], results["strings_total"], results["strings_per_tracker"],
        results["panels_recommended"], results["voltage_override"], results["annual_yield_kwh"],
        results["system_cost"], results["maintenance_cost_10yr"], results["solar_cost_per_kwh"],
        results["yaka_savings_10yr"], results["payback_years"], results["inverter_flag"], results["panel_array_flag"],
        f.get("notes",""),
    ))

    # Replace appliances
    execute("DELETE FROM solar_sizing_appliances WHERE sizing_id=%s", (sid,))
    for i, a in enumerate(results["appliances"], 1):
        execute("""
            INSERT INTO solar_sizing_appliances
                (sizing_id, line_no, name, load_type, power_w, annual_kwh, peak_w,
                 power_factor, quantity, hours_per_day, included, daily_wh)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (sid, i, a["name"], a.get("load_type","standard"),
              a["power_w"], a.get("annual_kwh",0), a.get("peak_w",0),
              a["power_factor"], a["quantity"], a["hours_per_day"],
              a["included"], a.get("daily_wh", 0)))

    # Replace BoM only if not locked (user customisations are preserved)
    if not bom_locked:
        execute("DELETE FROM solar_sizing_bom WHERE sizing_id=%s", (sid,))
        for i, item in enumerate(bom_items, 1):
            execute("""
                INSERT INTO solar_sizing_bom (sizing_id, line_no, description, uom, qty, unit_price, total)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (sid, i, item["description"], item["uom"], item["qty"], item["unit_price"], item["total"]))

    return sid


@app.route("/solar")
@login_required
def solar_list():
    rows = query("""
        SELECT s.*, q.quotation_no
        FROM solar_sizings s
        LEFT JOIN quotations q ON q.id = s.quotation_id
        ORDER BY s.created_at DESC
    """)
    return render_template("solar/list.html", sizings=rows)


def _solar_catalog():
    """Fetch catalog items for solar sizing form dropdowns.
    Returns dict of lists keyed by category, with spec_data parsed."""
    rows = query(
        "SELECT id, category, name, spec, sell_price, spec_data "
        "FROM catalog_items WHERE category IN ('Solar Panel','Inverter','Battery','Charge Controller') "
        "ORDER BY category, name"
    )
    result = {"Solar Panel": [], "Inverter": [], "Battery": [], "Charge Controller": []}
    for r in rows:
        sd = r["spec_data"]
        if isinstance(sd, str):
            try:
                sd = json.loads(sd)
            except Exception:
                sd = {}
        result.setdefault(r["category"], []).append({
            "id":        r["id"],
            "name":      r["name"],
            "spec":      r["spec"],
            "price":     r["sell_price"],
            "spec_data": sd or {},
        })
    return result


@app.route("/solar/new", methods=["GET", "POST"])
@login_required
def solar_new():
    if request.method == "POST":
        sid = _save_sizing(None, request.form)
        flash("Sizing calculated and saved.", "success")
        return redirect(url_for("solar_view", sid=sid))
    return render_template("solar/form.html", sizing=None,
                           appliances=None, default_appliances=_DEFAULT_APPLIANCES,
                           catalog=_solar_catalog())


@app.route("/solar/<sid>")
@login_required
def solar_view(sid):
    s = query_one("SELECT * FROM solar_sizings WHERE id=%s", (sid,))
    if not s:
        abort(404)
    appliances  = query("SELECT * FROM solar_sizing_appliances WHERE sizing_id=%s ORDER BY line_no", (sid,))
    bom         = query("SELECT * FROM solar_sizing_bom WHERE sizing_id=%s ORDER BY line_no", (sid,))
    bom_total   = sum(item["total"] for item in bom)
    # Engineering summary + financial appraisal reflect the actual BoM, not the
    # stale stored recommendation (see _reconcile_results_with_bom).
    r           = _reconcile_results_with_bom(s, [dict(b) for b in bom])
    quotation_no = None
    if s["quotation_id"]:
        qt = query_one("SELECT quotation_no FROM quotations WHERE id=%s", (s["quotation_id"],))
        quotation_no = qt["quotation_no"] if qt else None
    return render_template("solar/view.html", s=s, r=r, appliances=appliances,
                           bom=bom, bom_total=bom_total, quotation_no=quotation_no)


@app.route("/solar/<sid>/edit", methods=["GET", "POST"])
@login_required
def solar_edit(sid):
    s = query_one("SELECT * FROM solar_sizings WHERE id=%s", (sid,))
    if not s:
        abort(404)
    if request.method == "POST":
        _save_sizing(sid, request.form)
        flash("Sizing recalculated and saved.", "success")
        return redirect(url_for("solar_view", sid=sid))
    appliances = query("SELECT * FROM solar_sizing_appliances WHERE sizing_id=%s ORDER BY line_no", (sid,))
    return render_template("solar/form.html", sizing=s, appliances=appliances,
                           default_appliances=_DEFAULT_APPLIANCES, catalog=_solar_catalog())


@app.route("/solar/<sid>/to-quotation", methods=["POST"])
@login_required
def solar_to_quotation(sid):
    s = query_one("SELECT * FROM solar_sizings WHERE id=%s", (sid,))
    if not s:
        abort(404)
    bom = query("SELECT * FROM solar_sizing_bom WHERE sizing_id=%s ORDER BY line_no", (sid,))

    qid = str(uuid.uuid4())
    qno = next_quotation_number()
    execute("""
        INSERT INTO quotations (id, quotation_no, date, title, customer_name, customer_phone,
            customer_email, customer_address, delivery, validity, warranty, payment_terms,
            status, total_amount, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        qid, qno, date.today().isoformat(),
        f"Solar Installation — {s['client_name']}",
        s["client_name"], s["client_phone"] or "",
        s["client_email"] or "", s["client_site"] or "",
        "1-2 weeks after 70% material cost payment",
        "30 days", "12 months commencing on delivery date",
        "Cash / MM / EFT", "Pending",
        s["system_cost"] or 0,
        f"Generated from Solar Sizing. {s['utility_provider']} tariff: UGX {s['utility_tariff']:,.0f}/kWh. "
        f"Payback: {s['payback_years']:.1f} years.",
    ))
    for item in bom:
        execute("""
            INSERT INTO quotation_items (quotation_id, line_no, description, uom, qty, unit_price, total)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (qid, item["line_no"], item["description"], item["uom"],
              item["qty"], item["unit_price"], item["total"]))

    # Link sizing → quotation
    execute("UPDATE solar_sizings SET quotation_id=%s, status='Sent', updated_at=NOW() WHERE id=%s",
            (qid, sid))

    flash(f"Quotation {qno} created from sizing.", "success")
    return redirect(url_for("quotations_view", qid=qid))


@app.route("/solar/<sid>/pptx")
@login_required
def solar_pptx(sid):
    s = query_one("SELECT * FROM solar_sizings WHERE id=%s", (sid,))
    if not s:
        abort(404)
    appliances = query("SELECT * FROM solar_sizing_appliances WHERE sizing_id=%s ORDER BY line_no", (sid,))
    bom        = query("SELECT * FROM solar_sizing_bom WHERE sizing_id=%s ORDER BY line_no", (sid,))
    bom_list   = [dict(b) for b in bom]
    # Same reconciliation the detail page uses, so the proposal matches the BoM.
    results    = _reconcile_results_with_bom(s, bom_list)
    pptx_bytes = build_proposal(dict(s), results, [dict(a) for a in appliances], bom_list)
    safe_name  = s["client_name"].replace(" ", "_").replace("/", "-")
    return send_file(
        io.BytesIO(pptx_bytes),
        download_name=f"Solar_Proposal_{safe_name}.pptx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.route("/solar/<sid>/delete", methods=["POST"])
@login_required
def solar_delete(sid):
    execute("DELETE FROM solar_sizings WHERE id=%s", (sid,))
    flash("Sizing deleted.", "info")
    return redirect(url_for("solar_list"))


@app.route("/solar/<sid>/bom", methods=["GET", "POST"])
@login_required
def solar_bom_edit(sid):
    s = query("SELECT * FROM solar_sizings WHERE id=%s", (sid,))
    if not s:
        flash("Sizing not found.", "danger")
        return redirect(url_for("solar_list"))
    s = s[0]

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "regenerate":
            # Rebuild BoM from stored sizing values, unlock
            stored_params = {
                "system_voltage":                s["system_voltage"],
                "panel_wp":                      s["panel_wp"],
                "panel_isc":                     s["panel_isc"] or 0,
                "panel_cost":                    s["panel_cost"] or 0,
                "mppt_trackers":                 s["mppt_trackers"] or 1,
                "battery_ah":                    s["battery_ah"],
                "battery_voltage":               s["battery_voltage"],
                "battery_type":                  s["battery_type"],
                "battery_cost_each":             s["battery_cost_each"] or 0,
                "inverter_kw":                   s["inverter_kw"],
                "inverter_cost":                 s["inverter_cost"] or 0,
                "labour_transport":              s["labour_transport"] or 0,
                "utility_tariff":                s["utility_tariff"],
                "tariff_escalation":             (s["tariff_escalation"] or 0) / 100,
                "maintenance_cost_10yr":         s["maintenance_cost_10yr"] or 0,
            }
            stored_results = {
                "panels_recommended":  s["panels_recommended"],
                "total_batteries":     s["total_batteries"],
                "batteries_in_parallel": s["batteries_in_parallel"],
                "strings_per_tracker": s["strings_per_tracker"] or 1,
                "annual_yield_kwh":    s["annual_yield_kwh"],
                "maintenance_cost_10yr": s["maintenance_cost_10yr"] or 0,
            }
            bom_items = build_bom(stored_params, stored_results)
            bom_total = sum(item["total"] for item in bom_items)

            execute("DELETE FROM solar_sizing_bom WHERE sizing_id=%s", (sid,))
            for i, item in enumerate(bom_items, 1):
                execute("""
                    INSERT INTO solar_sizing_bom (sizing_id, line_no, description, uom, qty, unit_price, total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (sid, i, item["description"], item["uom"], item["qty"], item["unit_price"], item["total"]))

            # Recompute financials and unlock
            maint    = s["maintenance_cost_10yr"] or 0
            coo_10yr = bom_total + maint
            ten_yr   = (s["annual_yield_kwh"] or 0) * 10
            util_t   = s["utility_tariff"] or 897
            tariff_e = (s["tariff_escalation"] or 0) / 100
            if tariff_e > 0:
                ten_yr_grid = sum((s["annual_yield_kwh"] or 0) * util_t * ((1+tariff_e)**yr) for yr in range(10))
            else:
                ten_yr_grid = ten_yr * util_t
            annual_sav = (s["annual_yield_kwh"] or 0) * util_t
            execute("""
                UPDATE solar_sizings
                SET bom_locked=FALSE,
                    system_cost=%s, solar_cost_per_kwh=%s,
                    yaka_savings_10yr=%s, payback_years=%s,
                    updated_at=NOW()
                WHERE id=%s
            """, (
                round(bom_total, 0),
                round(coo_10yr / ten_yr, 2) if ten_yr > 0 else 0,
                round(ten_yr_grid - coo_10yr, 0),
                round(bom_total / annual_sav, 2) if annual_sav > 0 else 0,
                sid,
            ))
            flash("BoM regenerated from sizing.", "success")
            return redirect(url_for("solar_bom_edit", sid=sid))

        else:  # save custom BoM
            descs  = request.form.getlist("description[]")
            uoms   = request.form.getlist("uom[]")
            qtys   = request.form.getlist("qty[]")
            prices = request.form.getlist("unit_price[]")

            execute("DELETE FROM solar_sizing_bom WHERE sizing_id=%s", (sid,))
            bom_total = 0.0
            line = 0
            for desc, uom, qty_s, price_s in zip(descs, uoms, qtys, prices):
                if not desc.strip():
                    continue
                line += 1
                qty   = float(qty_s or 0)
                price = float(price_s or 0)
                total = round(qty * price, 0)
                bom_total += total
                execute("""
                    INSERT INTO solar_sizing_bom (sizing_id, line_no, description, uom, qty, unit_price, total)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (sid, line, desc.strip(), uom, qty, round(price, 0), total))

            # Recompute financials from new BoM total and lock
            maint    = s["maintenance_cost_10yr"] or 0
            coo_10yr = bom_total + maint
            ten_yr   = (s["annual_yield_kwh"] or 0) * 10
            util_t   = s["utility_tariff"] or 897
            tariff_e = (s["tariff_escalation"] or 0) / 100
            if tariff_e > 0:
                ten_yr_grid = sum((s["annual_yield_kwh"] or 0) * util_t * ((1+tariff_e)**yr) for yr in range(10))
            else:
                ten_yr_grid = ten_yr * util_t
            annual_sav = (s["annual_yield_kwh"] or 0) * util_t
            execute("""
                UPDATE solar_sizings
                SET bom_locked=TRUE,
                    system_cost=%s, solar_cost_per_kwh=%s,
                    yaka_savings_10yr=%s, payback_years=%s,
                    updated_at=NOW()
                WHERE id=%s
            """, (
                round(bom_total, 0),
                round(coo_10yr / ten_yr, 2) if ten_yr > 0 else 0,
                round(ten_yr_grid - coo_10yr, 0),
                round(bom_total / annual_sav, 2) if annual_sav > 0 else 0,
                sid,
            ))
            flash("BoM saved and locked.", "success")
            return redirect(url_for("solar_view", sid=sid))

    bom = query("SELECT * FROM solar_sizing_bom WHERE sizing_id=%s ORDER BY line_no", (sid,))
    return render_template("solar/bom_edit.html", s=s, bom=bom)


# ── Telegram bot ───────────────────────────────────────────────────────────────

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """Telegram sends every message/button press here via webhook."""
    update = request.get_json(force=True, silent=True) or {}
    _tg_handle_update(update)
    return "", 200


@app.route("/telegram/setup")
@login_required
def telegram_setup():
    """Register the webhook URL with Telegram. Visit once after each deployment."""
    import requests as _req
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    webhook = f"{os.environ.get('APP_BASE_URL', '')}/telegram/webhook"
    r = _req.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook, "allowed_updates": ["message", "callback_query"]},
        timeout=10,
    )
    return jsonify({"webhook_url": webhook, "telegram_response": r.json()})


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════

def _customer_stats(cid: str) -> dict:
    """Return total_quoted, total_collected, total_outstanding, job_count for a customer."""
    row = query_one("""
        SELECT
            COUNT(q.id)                                          AS job_count,
            COALESCE(SUM(q.total_amount), 0)                    AS total_quoted,
            COALESCE(SUM(r.paid), 0)                            AS total_collected,
            COALESCE(SUM(q.total_amount), 0)
              - COALESCE(SUM(r.paid), 0)                        AS total_outstanding
        FROM quotations q
        LEFT JOIN (
            SELECT quotation_id, SUM(amount_paid) AS paid
            FROM receipts GROUP BY quotation_id
        ) r ON r.quotation_id = q.id
        WHERE q.customer_id = %s
          AND q.status != 'Cancelled'
    """, (cid,))
    return dict(row) if row else {"job_count":0,"total_quoted":0,"total_collected":0,"total_outstanding":0}


def _customer_quotations(cid: str) -> list:
    rows = query("""
        SELECT q.id, q.quotation_no, q.date, q.status, q.total_amount,
               COALESCE(r.paid, 0) AS paid
        FROM quotations q
        LEFT JOIN (
            SELECT quotation_id, SUM(amount_paid) AS paid
            FROM receipts GROUP BY quotation_id
        ) r ON r.quotation_id = q.id
        WHERE q.customer_id = %s
        ORDER BY q.date DESC
    """, (cid,))
    return [dict(r) for r in rows]


def _next_customer_no() -> str:
    row = query_one("SELECT 'CUST-' || LPAD(nextval('customer_no_seq')::TEXT, 4, '0') AS no")
    return row["no"]


@app.route("/customers")
@login_required
def customers_list():
    search = request.args.get("q", "").strip()
    sql = """
        SELECT c.id, c.customer_no, c.name, c.phone, c.email,
               COUNT(q.id) AS job_count,
               COALESCE(SUM(q.total_amount),0) - COALESCE(SUM(r.paid),0) AS outstanding
        FROM customers c
        LEFT JOIN quotations q ON q.customer_id = c.id AND q.status != 'Cancelled'
        LEFT JOIN (
            SELECT quotation_id, SUM(amount_paid) AS paid FROM receipts GROUP BY quotation_id
        ) r ON r.quotation_id = q.id
    """
    params = []
    if search:
        sql += " WHERE c.name ILIKE %s OR c.phone ILIKE %s"
        params += [f"%{search}%", f"%{search}%"]
    sql += " GROUP BY c.id ORDER BY c.name"
    customers = [dict(r) for r in query(sql, params or None)]
    return render_template("customers/list.html", customers=customers, search=search)


@app.route("/customers/new", methods=["GET", "POST"])
@login_required
def customers_new():
    if request.method == "POST":
        f = request.form
        cno = _next_customer_no()
        execute("""
            INSERT INTO customers (id, customer_no, name, phone, email, address, notes)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
        """, (cno, f["name"].strip(), f.get("phone","").strip(),
              f.get("email","").strip(), f.get("address","").strip(),
              f.get("notes","").strip()))
        flash(f"Customer {cno} created.", "success")
        return redirect(url_for("customers_list"))
    return render_template("customers/form.html", customer=None)


@app.route("/customers/<cid>")
@login_required
def customers_profile(cid):
    customer = query_one("SELECT * FROM customers WHERE id=%s", (cid,))
    if not customer:
        abort(404)
    stats      = _customer_stats(cid)
    quotations = _customer_quotations(cid)
    return render_template("customers/profile.html",
                           customer=dict(customer), stats=stats, quotations=quotations)


@app.route("/customers/<cid>/edit", methods=["GET", "POST"])
@login_required
def customers_edit(cid):
    customer = query_one("SELECT * FROM customers WHERE id=%s", (cid,))
    if not customer:
        abort(404)
    if request.method == "POST":
        f = request.form
        execute("""
            UPDATE customers SET name=%s, phone=%s, email=%s, address=%s, notes=%s,
                                 updated_at=NOW()
            WHERE id=%s
        """, (f["name"].strip(), f.get("phone","").strip(), f.get("email","").strip(),
              f.get("address","").strip(), f.get("notes","").strip(), cid))
        flash("Customer updated.", "success")
        return redirect(url_for("customers_profile", cid=cid))
    return render_template("customers/form.html", customer=dict(customer))


@app.route("/customers/<cid>/send-statement", methods=["POST"])
@login_required
def customers_send_statement(cid):
    customer = query_one("SELECT * FROM customers WHERE id=%s", (cid,))
    if not customer:
        abort(404)
    customer  = dict(customer)
    stats     = _customer_stats(cid)
    quotations = _customer_quotations(cid)
    stmt_url  = url_for("statement_public", token=customer["statement_token"], _external=True)
    try:
        pdf_bytes = build_statement_pdf(customer, quotations, stats)
        import threading
        threading.Thread(
            target=send_customer_statement,
            args=(customer, stats, pdf_bytes, stmt_url),
            daemon=True,
        ).start()
        flash(f"Statement sent to {customer['email']}. Share this link too: {stmt_url}", "success")
    except Exception as e:
        flash(f"Could not generate statement PDF: {e}", "danger")
    return redirect(url_for("customers_profile", cid=cid))


@app.route("/customers/<cid>/regenerate-token", methods=["POST"])
@login_required
def customers_regenerate_token(cid):
    execute("UPDATE customers SET statement_token=gen_random_uuid() WHERE id=%s", (cid,))
    flash("Statement link regenerated. The old link is now invalid.", "info")
    return redirect(url_for("customers_profile", cid=cid))


# ── Public statement (no login — token-gated) ──────────────────────────────────

@app.route("/s/<token>")
def statement_public(token):
    customer = query_one("SELECT * FROM customers WHERE statement_token=%s::uuid", (token,))
    if not customer:
        abort(404)
    customer   = dict(customer)
    stats      = _customer_stats(customer["id"])
    quotations = _customer_quotations(customer["id"])
    as_of    = __import__("datetime").date.today().strftime("%-d %B %Y")
    back_cid = request.args.get("back", "")
    return render_template("customers/statement_public.html",
                           customer=customer, stats=stats,
                           quotations=quotations, as_of=as_of,
                           back_cid=back_cid)


@app.route("/s/<token>/pdf")
def statement_pdf(token):
    customer = query_one("SELECT * FROM customers WHERE statement_token=%s::uuid", (token,))
    if not customer:
        abort(404)
    customer   = dict(customer)
    stats      = _customer_stats(customer["id"])
    quotations = _customer_quotations(customer["id"])
    pdf_bytes  = build_statement_pdf(customer, quotations, stats)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Statement_{customer['customer_no']}.pdf",
    )


# ── Customer JSON search (for quotation form picker) ──────────────────────────

@app.route("/customers/search.json")
@login_required
def customers_search_json():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    rows = query("""
        SELECT id, customer_no, name, phone, email, address
        FROM customers
        WHERE name ILIKE %s OR phone ILIKE %s
        ORDER BY name LIMIT 10
    """, (f"%{q}%", f"%{q}%"))
    return jsonify([dict(r) for r in rows])


@app.route("/admin/test-email")
def test_email():
    """Resend API test — returns success or the actual error."""
    import requests as _req
    key      = os.environ.get("SENDGRID_API_KEY", "")
    from_    = os.environ.get("EMAIL_FROM", "rincoltech@gmail.com")
    notify_to = os.environ.get("NOTIFY_EMAILS", "arinda.hillary@gmail.com")
    to_list  = [e.strip() for e in notify_to.split(",") if e.strip()]
    try:
        r = _req.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": e} for e in to_list]}],
                "from": {"email": from_, "name": "Rincol Tech Solutions"},
                "subject": "Rincol ERP — email test",
                "content": [{"type": "text/html", "value": "<p>SendGrid is working.</p>"}],
            },
            timeout=10,
        )
        return jsonify({"status": "ok" if r.status_code == 202 else "error",
                        "sg_status": r.status_code,
                        "from": from_, "to": to_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
