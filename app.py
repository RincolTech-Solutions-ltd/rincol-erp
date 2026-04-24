"""Rincol Web ERP — Flask Application."""
import os
import io
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
from utils.pdf import build_quotation_pdf, build_receipt_pdf


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
        "pending":     query_one("SELECT COUNT(*) AS n FROM quotations WHERE status='Pending'")["n"],
        "outstanding": query_one(
            "SELECT COALESCE(SUM(q.total_amount - COALESCE(r.paid,0)),0) AS n "
            "FROM quotations q "
            "LEFT JOIN (SELECT quotation_id, SUM(amount_paid) AS paid FROM receipts "
            "           WHERE quotation_id IS NOT NULL GROUP BY quotation_id) r "
            "  ON r.quotation_id=q.id "
            "WHERE q.status NOT IN ('Cancelled','Pending')")["n"],
        "maintenance": query_one("SELECT COUNT(*) AS n FROM maintenance_records WHERE status='Open'")["n"],
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
    sql += " ORDER BY q.created_at DESC"
    rows = query(sql, params)
    return render_template("quotation/list.html", quotations=rows, status=status, search=search)


@app.route("/quotations/new", methods=["GET", "POST"])
@login_required
def quotations_new():
    templates = query("SELECT id, name FROM system_templates ORDER BY sort_order")
    catalog   = query("SELECT id, category, name, spec, uom, sell_price FROM catalog_items ORDER BY category, name")
    if request.method == "POST":
        return _save_quotation(None)
    return render_template("quotation/form.html", q=None, templates=templates, catalog=catalog,
                           qno=next_quotation_number())


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
    return render_template("quotation/view.html", q=q, items=items,
                           receipts=receipts, execs=execs, paid=paid, balance=balance)


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
    f   = request.form
    qid = qid or str(uuid.uuid4())
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
    grand     = subtotal + vat_amt

    execute("""
        INSERT INTO quotations (id, quotation_no, date, title, customer_name, customer_phone,
            customer_email, customer_address, delivery, validity, warranty,
            payment_terms, status, total_amount, vat_rate, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
            quotation_no=EXCLUDED.quotation_no, date=EXCLUDED.date,
            title=EXCLUDED.title, customer_name=EXCLUDED.customer_name,
            customer_phone=EXCLUDED.customer_phone, customer_email=EXCLUDED.customer_email,
            customer_address=EXCLUDED.customer_address, delivery=EXCLUDED.delivery,
            validity=EXCLUDED.validity, warranty=EXCLUDED.warranty,
            payment_terms=EXCLUDED.payment_terms, status=EXCLUDED.status,
            total_amount=EXCLUDED.total_amount, vat_rate=EXCLUDED.vat_rate,
            notes=EXCLUDED.notes, updated_at=NOW()
    """, (qid, qno, f.get("date") or date.today().isoformat(),
          f.get("title","Quotation"), f["customer_name"], f.get("customer_phone",""),
          f.get("customer_email",""), f.get("customer_address",""),
          f.get("delivery",""), f.get("validity","30 days"), f.get("warranty",""),
          f.get("payment_terms","Cash / MM / EFT"), f.get("status","Pending"),
          grand, vat_rate, f.get("notes","")))

    execute("DELETE FROM quotation_items WHERE quotation_id=%s", (qid,))
    for it in items:
        execute("INSERT INTO quotation_items (quotation_id,line_no,description,uom,qty,unit_price,total) VALUES (%s,%s,%s,%s,%s,%s,%s)", it)

    flash("Quotation saved.", "success")
    return redirect(url_for("quotations_view", qid=qid))


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
    # One execution record per job — upsert on quotation_id
    existing = query_one("SELECT id FROM job_executions WHERE quotation_id=%s LIMIT 1", (qid,))
    if existing:
        execute(
            "UPDATE job_executions SET executor_name=%s, executor_payment=%s, "
            "execution_date=%s, notes=%s WHERE id=%s",
            (request.form["executor_name"],
             float(request.form.get("executor_payment", 0)),
             request.form.get("execution_date") or None,
             request.form.get("notes", ""),
             existing["id"])
        )
        flash("Execution record updated.", "success")
    else:
        execute(
            "INSERT INTO job_executions (quotation_id, executor_name, executor_payment, execution_date, notes) "
            "VALUES (%s,%s,%s,%s,%s)",
            (qid, request.form["executor_name"],
             float(request.form.get("executor_payment", 0)),
             request.form.get("execution_date") or None,
             request.form.get("notes", ""))
        )
        flash("Execution record saved.", "success")
    return redirect(url_for("quotations_view", qid=qid))


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
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone, total_amount FROM quotations ORDER BY date DESC LIMIT 100")
    if request.method == "POST":
        f    = request.form
        rid  = str(uuid.uuid4())
        rno  = f.get("receipt_no","").strip() or f"RCT-{date.today().year}-001"
        fig  = float(f.get("amount_fig",0))
        paid = float(f.get("amount_paid",0))
        qid  = f.get("quotation_id") or None
        mid  = f.get("maintenance_id") or None
        execute("""INSERT INTO receipts
            (id,receipt_no,date,customer_name,customer_phone,customer_email,
             customer_address,being_for,amount_fig,amount_paid,balance,cheque_no,
             issued_name,received_name,collected_by,quotation_id,maintenance_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, rno, f.get("date") or date.today().isoformat(),
             f["customer_name"], f.get("customer_phone",""), f.get("customer_email",""),
             f.get("customer_address",""), f.get("being_for",""),
             fig, paid, fig-paid, f.get("cheque_no",""),
             f.get("issued_name",""), f.get("received_name",""),
             f.get("collected_by","Hillary"), qid, mid))
        flash("Receipt saved.", "success")
        return redirect(url_for("receipts_view", rid=rid))
    prefill_qid = request.args.get("qid")
    prefill_mid = request.args.get("mid")
    # If coming from a maintenance record, prefill client details
    prefill_maint = None
    if prefill_mid:
        prefill_maint = query_one("SELECT * FROM maintenance_records WHERE id=%s", (prefill_mid,))
    return render_template("receipt/form.html", r=None, quotations=quotations,
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
            issued_name=%s, received_name=%s, collected_by=%s, quotation_id=%s
            WHERE id=%s""",
            (f.get("receipt_no",""), f.get("date") or date.today().isoformat(),
             f["customer_name"], f.get("customer_phone",""), f.get("customer_email",""),
             f.get("customer_address",""), f.get("being_for",""),
             fig, paid, fig - paid, f.get("cheque_no",""),
             f.get("issued_name",""), f.get("received_name",""),
             f.get("collected_by","Hillary"), qid, rid))
        flash("Receipt updated.", "success")
        return redirect(url_for("receipts_view", rid=rid))
    quotations = query("SELECT id, quotation_no, customer_name, customer_phone, total_amount FROM quotations ORDER BY date DESC LIMIT 100")
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
             executor_name,executor_payment,status,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f.get("linked_quotation_id") or None,
             f["client_name"], f.get("client_phone",""),
             f.get("visit_date") or date.today().isoformat(),
             f.get("type","Paid"), f.get("problem",""), f.get("parts_used",""),
             float(f.get("parts_cost",0)), float(f.get("labour_fee",0)),
             f.get("paid_by","Hillary"),
             int(f.get("h_ratio",100)), int(f.get("d_ratio",0)),
             f.get("executor_name",""), float(f.get("executor_payment",0)),
             f.get("status","Open"), f.get("notes","")))
        flash("Maintenance record saved.", "success")
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
            executor_payment=%s,status=%s,notes=%s WHERE id=%s""",
            (f.get("linked_quotation_id") or None,
             f["client_name"],f.get("client_phone",""),f.get("visit_date"),
             f.get("type","Paid"),f.get("problem",""),f.get("parts_used",""),
             float(f.get("parts_cost",0)),float(f.get("labour_fee",0)),
             f.get("paid_by","Hillary"),
             int(f.get("h_ratio",100)),int(f.get("d_ratio",0)),
             f.get("executor_name",""),float(f.get("executor_payment",0)),
             f.get("status","Open"),f.get("notes",""),mid))
        flash("Record updated.","success")
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
        f  = request.form
        iid = item_id or f.get("id") or str(uuid.uuid4())[:8].upper()
        execute("""INSERT INTO catalog_items (id,category,name,spec,uom,buy_price,sell_price,supplier_id,notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
            category=EXCLUDED.category,name=EXCLUDED.name,spec=EXCLUDED.spec,
            uom=EXCLUDED.uom,buy_price=EXCLUDED.buy_price,sell_price=EXCLUDED.sell_price,
            supplier_id=EXCLUDED.supplier_id,notes=EXCLUDED.notes""",
            (iid,f["category"],f["name"],f.get("spec",""),f.get("uom","pc"),
             int(f.get("buy_price",0)),int(f.get("sell_price",0)),
             f.get("supplier_id",""),f.get("notes","")))
        flash("Item saved.","success")
        return redirect(url_for("catalog_list"))
    categories = ["Battery","Inverter","Solar Panel","Charge Controller","Cable","Accessory","Service"]
    return render_template("catalog/form.html", item=item, categories=categories)


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
        return redirect(url_for("balancing_view", jid=jid))

    # ?qid= prefill for new jobs
    prefill = {}
    if not jid:
        qid = request.args.get("qid")
        if qid:
            q = query_one("SELECT * FROM quotations WHERE id=%s", (qid,))
            if q:
                exe = query_one(
                    "SELECT executor_name, executor_payment, execution_date FROM job_executions "
                    "WHERE quotation_id=%s ORDER BY execution_date DESC NULLS LAST LIMIT 1",
                    (qid,)
                )
                prefill_spend = []
                if exe and exe.get("executor_payment") and float(exe["executor_payment"] or 0) > 0:
                    prefill_spend.append({
                        "description": f"{exe['executor_name'] or 'Executor'} labour",
                        "paid_by": "Dennis",
                        "amount": float(exe["executor_payment"]),
                    })
                prefill = {
                    "job_name":            f"{q['customer_name']} — {q['quotation_no']}",
                    "quoted":              q["total_amount"],
                    "linked_quotation_id": qid,
                    "date": (exe["execution_date"].isoformat()
                             if exe and exe.get("execution_date") else ""),
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
    f = request.form
    execute(
        "INSERT INTO balancing_settlements (balancing_job_id, date, amount, from_person, notes) "
        "VALUES (%s,%s,%s,%s,%s)",
        (jid, f.get("date") or date.today().isoformat(),
         float(f["amount"]), f.get("from_person", "Hillary"), f.get("notes", ""))
    )
    flash("Settlement recorded.", "success")
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
    elif status == "all":
        pass
    else:
        sql += " AND t.status != 'Done'"
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
        return redirect(url_for("tasks_list"))
    quotations = query("SELECT id, quotation_no, customer_name FROM quotations ORDER BY date DESC LIMIT 100")
    return render_template("tasks/form.html", task=task, quotations=quotations)


@app.route("/tasks/<int:tid>/done", methods=["POST"])
@login_required
def tasks_done(tid):
    execute("UPDATE tasks SET status='Done', updated_at=NOW() WHERE id=%s", (tid,))
    flash("Task marked done.", "success")
    return redirect(url_for("tasks_list"))


@app.route("/tasks/<int:tid>/delete", methods=["POST"])
@login_required
def tasks_delete(tid):
    execute("DELETE FROM tasks WHERE id=%s", (tid,))
    flash("Task deleted.", "success")
    return redirect(url_for("tasks_list"))


# ── API: template items ────────────────────────────────────────────────────────
@app.route("/api/template/<tid>")
@login_required
def api_template(tid):
    items = query(
        "SELECT DISTINCT ON (ti.description) ti.*, ci.sell_price FROM template_items ti "
        "LEFT JOIN catalog_items ci ON ci.id=ti.catalog_item_id "
        "WHERE ti.template_id=%s ORDER BY ti.description, ti.id", (tid,))
    return jsonify([dict(i) for i in items])


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
