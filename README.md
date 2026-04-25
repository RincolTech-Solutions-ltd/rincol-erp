# Rincol Web ERP

Internal business management system for Rincol Tech Solutions Ltd — a solar installation and maintenance company in Uganda. Built for two users: **Hillary Arinda** (admin, quotes and manages) and **Dennis Kaweesi** (field technician, executes jobs).

**Live URL:** https://rincol-erp.onrender.com
**Stack:** Python 3.12 · Flask · Supabase (PostgreSQL + Auth) · Bootstrap 5 dark · Vanilla JS · Gunicorn · Render (hosting)

---

## Table of Contents

1. [Business Context](#1-business-context)
2. [Architecture Overview](#2-architecture-overview)
3. [How Flask Works — The Big Picture](#3-how-flask-works--the-big-picture)
4. [How Supabase Works](#4-how-supabase-works)
5. [Database Design](#5-database-design)
6. [Table Relationships](#6-table-relationships)
7. [Module Reference](#7-module-reference)
8. [Balancing — Deep Dive](#8-balancing--deep-dive)
9. [Maintenance P&L — Deep Dive](#9-maintenance-pl--deep-dive)
10. [How Pages Are Served](#10-how-pages-are-served)
11. [PWA Setup](#11-pwa-setup)
12. [File Structure](#12-file-structure)
13. [Local Development](#13-local-development)
14. [Cloud Deployment (Render)](#14-cloud-deployment-render)
15. [Environment Variables](#15-environment-variables)
16. [Key Design Decisions](#16-key-design-decisions)

---

## 1. Business Context

Rincol Tech Solutions installs solar power systems for homes and businesses. The workflow is:

```
Customer inquiry → Quotation → Approval → Installation → Receipt → Balancing
                                                       ↓
                                                  Maintenance (warranty / paid visits)
```

Hillary quotes jobs and manages money. Dennis executes installations in the field. After a job, they split profits — Dennis takes 55%, Hillary 45% by default. This split is tracked in the **Balancing** module.

Maintenance visits (warranty or paid) happen after a job is completed. These are tracked separately from balancing because they are a post-profit event — Hillary usually bears the cost.

---

## 2. Architecture Overview

```
Browser (HTML form submit / link click)
        │
        ▼
Render (cloud host) — runs Docker container
        │
        ▼
Gunicorn (2 worker processes)
        │
        ▼
Flask app (app.py) — receives HTTP request, runs Python logic
        │
        ├── psycopg2 (ThreadedConnectionPool) ──▶ Supabase PostgreSQL (database)
        │       reads and writes all business data
        │
        ├── supabase-py client ──────────────────▶ Supabase Auth
        │       login / logout only
        │
        ├── Jinja2 template engine ──────────────▶ renders HTML
        │       sends complete HTML page back to browser
        │
        └── ReportLab ──────────────────────────▶ generates PDF in memory
                sends as file download
```

**Key point:** There is no JavaScript framework (no React, Vue, etc.). The server renders complete HTML pages. JavaScript only handles UI interactivity (column resizing, line item calculations, drag-to-reorder) — it never talks directly to the database.

---

## 3. How Flask Works — The Big Picture

Flask is a Python web framework. It maps URLs to Python functions (called *views* or *routes*). When a browser visits a URL, Flask calls the matching function, which runs queries, builds a data dictionary, and returns an HTML page.

### Request lifecycle

```
1. Browser sends: GET /quotations/abc123
2. Flask matches route: @app.route("/quotations/<qid>")
3. Flask calls: quotations_view(qid="abc123")
4. Function runs SQL queries via psycopg2
5. Function calls: render_template("quotation/view.html", q=q, items=items, ...)
6. Jinja2 fills the template with Python data
7. Flask returns the complete HTML string
8. Browser renders it
```

### How form submissions work

HTML forms use `method="POST"`. The browser collects all input values, encodes them, and sends them to the server. Flask reads them with `request.form["field_name"]`.

```python
# In app.py:
@app.route("/quotations/new", methods=["GET", "POST"])
def quotations_new():
    if request.method == "POST":
        # Form was submitted — save to DB, redirect
        return _save_quotation(None)
    # Page visit — show empty form
    return render_template("quotation/form.html", ...)
```

The same URL handles both "show me the form" (GET) and "save what I filled in" (POST).

### The `@login_required` decorator

Every route (except `/login`) is wrapped with `@login_required`. This is a Python decorator — a function that wraps another function. It checks if the user's session exists before running the view:

```python
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth_login"))  # kick to login page
        return f(*args, **kwargs)                   # proceed normally
    return decorated
```

### Flask sessions

Flask stores user data in a browser cookie (encrypted with `FLASK_SECRET_KEY`). After login, `session["user"]` contains `{id, email, name}`. This persists across requests — it is how Flask knows the user is still logged in.

### Jinja2 templates

Templates are HTML files with `{{ variable }}` and `{% logic %}` blocks:

```html
<!-- templates/quotation/view.html -->
<h1>{{ q.customer_name }}</h1>
{% for item in items %}
  <tr>
    <td>{{ item.description }}</td>
    <td>{{ "{:,.0f}".format(item.total) }}</td>
  </tr>
{% endfor %}
```

The `q` and `items` variables come from the Python `render_template(...)` call. Jinja2 fills them in and produces the final HTML.

### `url_for()` — how links are built

Instead of hardcoding `/quotations/abc123`, Flask builds URLs from function names:

```python
url_for("quotations_view", qid="abc123")  # → "/quotations/abc123"
url_for("dashboard")                       # → "/"
```

This means renaming a URL path never breaks internal links — you only change the route decorator.

---

## 4. How Supabase Works

Supabase is a managed cloud database platform built on PostgreSQL. It provides:

### 4.1 PostgreSQL database

A full PostgreSQL database hosted in the cloud. You run SQL in their web-based SQL Editor to create tables, run migrations, and inspect data. This is where all business data lives.

### 4.2 Auth (authentication service)

Supabase Auth manages user accounts (email + password). It has its own `auth.users` table (separate from your business tables). It issues JWTs (JSON Web Tokens) on login.

**How login works in this app:**

```python
# app.py — login route
res = supabase.auth.sign_in_with_password({"email": email, "password": password})
session["user"] = {
    "id":    res.user.id,
    "email": res.user.email,
    "name":  res.user.user_metadata.get("full_name", ...),
}
session["sb_access_token"]  = res.session.access_token
session["sb_refresh_token"] = res.session.refresh_token
```

The `supabase-py` client sends credentials to Supabase Auth. Supabase validates them and returns a user object + JWT tokens. We store the user info in Flask's session (cookie). We do NOT use the JWT for subsequent database queries — we use psycopg2 directly with the database password (more on that below).

**Creating users:**
Users must be created in Supabase Dashboard → Authentication → Users. You cannot register from the app UI — it is invite-only by design. Set `full_name` in the user metadata so it appears in the sidebar.

### 4.3 Two clients — why both?

The app uses **two separate clients** to talk to Supabase:

| Client | Library | Used for |
|--------|---------|----------|
| `supabase` (Python SDK) | `supabase-py` | Authentication only (sign_in, sign_out) |
| psycopg2 pool | `psycopg2` | All SQL queries — SELECT, INSERT, UPDATE, DELETE |

Why not use the Supabase Python SDK for everything? Because psycopg2 gives full SQL control — complex JOINs, LATERAL subqueries, ON CONFLICT upserts, window functions. The Supabase SDK's query builder is good for simple CRUD but limited for complex queries.

### 4.4 Connection string

The database URL format:
```
postgresql://postgres.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres
```

The **session pooler** URL (from Supabase → Connect → Session pooler) is required for hosted environments like Render. The direct `db.xxx.supabase.co:5432` URL only works from networks with IPv6 support or explicit allowlisting.

### 4.5 Row Level Security (RLS)

Supabase enables RLS by default on new tables. **RLS must be disabled** on all tables for this app, because psycopg2 connects as the `postgres` superuser (bypasses RLS anyway), but the Supabase dashboard may block the SQL Editor if RLS is misconfigured. To disable:

```sql
ALTER TABLE quotations DISABLE ROW LEVEL SECURITY;
-- repeat for every table
```

Or, when creating tables in the SQL Editor, add `DISABLE ROW LEVEL SECURITY` to each `CREATE TABLE`.

---

## 5. Database Design

### Design principles

- **UUIDs for business entities** (quotations, receipts, balancing jobs) — prevents ID guessing and allows client-side ID generation.
- **SERIAL for sub-records** (line items, spend lines, payments) — auto-incrementing integers, simpler for records that are always created server-side.
- **TEXT for status fields** — readable strings (`'Pending'`, `'Approved'`) rather than integers. Easier to debug, no lookup table needed.
- **REAL for money** — PostgreSQL REAL (float) is used for UGX amounts. For a currency with no decimals (UGX), REAL is fine. A production multi-currency system should use NUMERIC(15,2).
- **TIMESTAMPTZ for timestamps** — stores timezone-aware timestamps. Always stored in UTC, displayed in local time.
- **Additive migrations only** — never drop columns from a live database. Add columns with `IF NOT EXISTS` and defaults so old rows are still valid.

### Full schema (current state)

Run `schema.sql` first, then `migration.sql`. Both are idempotent (safe to re-run).

#### `catalog_items`
Product and service catalog. 54 items pre-seeded across 7 categories.
```sql
CREATE TABLE catalog_items (
    id          TEXT PRIMARY KEY,          -- e.g. "BAT001", "INV003"
    category    TEXT NOT NULL,             -- Battery | Inverter | Solar Panel | ...
    name        TEXT NOT NULL,
    spec        TEXT DEFAULT '',           -- technical spec string
    uom         TEXT DEFAULT 'pc',         -- unit of measure: pc, m, kg, set
    buy_price   INTEGER DEFAULT 0,         -- what Rincol pays supplier (UGX)
    sell_price  INTEGER DEFAULT 0,         -- what customer pays (UGX)
    supplier_id TEXT DEFAULT '',           -- FK to service_providers (soft ref)
    notes       TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

#### `service_providers`
Suppliers and subcontractors. 6 pre-seeded.
```sql
CREATE TABLE service_providers (
    id             TEXT PRIMARY KEY,       -- e.g. "SUP-ABC123"
    name           TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    phone          TEXT DEFAULT '',
    email          TEXT DEFAULT '',
    location       TEXT DEFAULT '',
    categories     TEXT DEFAULT '',        -- comma-separated categories they supply
    notes          TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

#### `system_templates`
Quick Build templates — pre-built quotation kits.
```sql
CREATE TABLE system_templates (
    id          TEXT PRIMARY KEY,          -- e.g. "TPL-700VA"
    name        TEXT NOT NULL,             -- "Small System — 700VA 12V"
    description TEXT DEFAULT '',
    sort_order  INTEGER DEFAULT 0
);
```

#### `template_items`
Line items for each template.
```sql
CREATE TABLE template_items (
    id              SERIAL PRIMARY KEY,
    template_id     TEXT REFERENCES system_templates(id) ON DELETE CASCADE,
    catalog_item_id TEXT,                  -- optional link to catalog_items
    description     TEXT,
    uom             TEXT DEFAULT 'pc',
    qty             REAL DEFAULT 1
);
```
`ON DELETE CASCADE` means: delete the template → all its items are deleted automatically.

#### `quotations`
The core table. One row per quotation.
```sql
CREATE TABLE quotations (
    id              TEXT PRIMARY KEY,      -- UUID, generated in Python
    quotation_no    TEXT UNIQUE NOT NULL,  -- "QT-2026-103" — human-readable
    date            DATE NOT NULL,
    title           TEXT DEFAULT 'Quotation',
    customer_name   TEXT NOT NULL,
    customer_phone  TEXT DEFAULT '',
    customer_email  TEXT DEFAULT '',
    customer_address TEXT DEFAULT '',
    delivery        TEXT DEFAULT '1-2 days after 70% material cost payment',
    validity        TEXT DEFAULT '30 days',
    warranty        TEXT DEFAULT '12 months commencing on the delivery date',
    payment_terms   TEXT DEFAULT 'Cash / MM / EFT',
    status          TEXT DEFAULT 'Pending',
    -- status values: Pending | Approved | In Progress | Completed | Cancelled
    total_amount    REAL DEFAULT 0,        -- VAT-inclusive grand total
    vat_rate        NUMERIC(5,2),          -- NULL = no VAT; 18.00 = 18% VAT applied
    notes           TEXT DEFAULT '',
    sig_issued_url  TEXT DEFAULT '',       -- reserved for signature image URL
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**VAT logic:** `vat_rate` is NULL when no VAT is applied. When set (e.g. `18.00`), `total_amount` stores the VAT-inclusive grand total. To recover subtotal on the view page: `subtotal = total_amount / (1 + vat_rate/100)`.

**Payment status is computed, not stored.** It is derived at query time by summing receipts linked to the quotation. There is no `payment_status` column.

#### `quotation_items`
Line items for each quotation.
```sql
CREATE TABLE quotation_items (
    id           SERIAL PRIMARY KEY,
    quotation_id TEXT REFERENCES quotations(id) ON DELETE CASCADE,
    line_no      INTEGER NOT NULL,         -- display order (1, 2, 3...)
    description  TEXT NOT NULL,
    uom          TEXT DEFAULT 'pc',
    qty          REAL DEFAULT 1,
    unit_price   REAL DEFAULT 0,
    total        REAL DEFAULT 0            -- qty × unit_price, stored for convenience
);
```

When a quotation is saved, all existing line items are deleted first (`DELETE FROM quotation_items WHERE quotation_id=...`), then re-inserted fresh. This is simpler than tracking which rows were added/removed/reordered.

#### `receipts`
Every receipt issued to a customer. The single source of truth for money received.
```sql
CREATE TABLE receipts (
    id               TEXT PRIMARY KEY,     -- UUID
    receipt_no       TEXT UNIQUE NOT NULL, -- "RCT-2026-001"
    date             DATE NOT NULL,
    customer_name    TEXT NOT NULL,
    customer_phone   TEXT DEFAULT '',
    customer_email   TEXT DEFAULT '',
    customer_address TEXT DEFAULT '',
    being_for        TEXT DEFAULT '',      -- description of what payment is for
    amount_fig       REAL DEFAULT 0,       -- total figure on the receipt
    amount_paid      REAL DEFAULT 0,       -- actual cash collected this receipt
    balance          REAL DEFAULT 0,       -- amount_fig - amount_paid (outstanding)
    cheque_no        TEXT DEFAULT '',
    issued_name      TEXT DEFAULT '',      -- name of person who issued the receipt
    received_name    TEXT DEFAULT '',      -- name of person who received (customer)
    collected_by     TEXT DEFAULT 'Hillary', -- Hillary | Dennis — who physically got the cash
    quotation_id     TEXT REFERENCES quotations(id),  -- optional link to quotation
    maintenance_id   INTEGER REFERENCES maintenance_records(id), -- optional link to maintenance
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

A receipt can be:
- **Standalone** — no `quotation_id`, no `maintenance_id` (e.g. a deposit receipt)
- **Linked to a quotation** — tracked in balancing as customer revenue
- **Linked to a maintenance record** — tracked in maintenance P&L

#### `payments`
Legacy table — kept for historical data but no longer used in the UI. Do not delete (existing payment records still reference it). Balancing reads from `receipts` instead.

#### `job_executions`
Records who executed each installation job and what they were paid.
```sql
CREATE TABLE job_executions (
    id               SERIAL PRIMARY KEY,
    quotation_id     TEXT REFERENCES quotations(id) ON DELETE CASCADE,
    executor_name    TEXT NOT NULL,
    executor_payment REAL DEFAULT 0,       -- cash paid to executor (UGX)
    execution_date   DATE,
    notes            TEXT DEFAULT ''
);
```
One record per quotation (enforced in code with an upsert pattern). When creating a balancing job from the dashboard "unbalanced jobs" list, executor payment is pre-filled as a spend line.

#### `maintenance_records`
Post-installation visits — warranty (free) or paid service calls.
```sql
CREATE TABLE maintenance_records (
    id                   SERIAL PRIMARY KEY,
    linked_quotation_id  TEXT REFERENCES quotations(id) ON DELETE SET NULL,
    -- ON DELETE SET NULL: if the quotation is deleted, the maintenance record stays,
    -- just loses its link. This is gentler than CASCADE (which would delete the record).
    client_name          TEXT NOT NULL,
    client_phone         TEXT DEFAULT '',
    visit_date           DATE NOT NULL,
    type                 TEXT DEFAULT 'Paid',  -- Warranty | Paid
    problem              TEXT DEFAULT '',
    parts_used           TEXT DEFAULT '',
    parts_cost           REAL DEFAULT 0,
    labour_fee           REAL DEFAULT 0,
    paid_by              TEXT DEFAULT 'Hillary',  -- who fronted the money
    h_ratio              INTEGER DEFAULT 100,  -- Hillary's share of profit (%)
    d_ratio              INTEGER DEFAULT 0,    -- Dennis's share of profit (%)
    executor_name        TEXT DEFAULT '',
    executor_payment     REAL DEFAULT 0,
    status               TEXT DEFAULT 'Open',  -- Open | Resolved | Pending Parts
    notes                TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
```

#### `balancing_jobs`
One record per job that has been balanced (profit split between Hillary and Dennis).
```sql
CREATE TABLE balancing_jobs (
    id                   TEXT PRIMARY KEY,   -- short UUID e.g. "A3B9F1C2"
    job_name             TEXT NOT NULL,
    linked_quotation_id  TEXT REFERENCES quotations(id),
    date                 DATE NOT NULL,
    quoted               REAL DEFAULT 0,     -- agreed job value (from quotation)
    h_ratio              INTEGER DEFAULT 45, -- Hillary's profit share %
    d_ratio              INTEGER DEFAULT 55, -- Dennis's profit share %
    status               TEXT DEFAULT 'Open',
    notes                TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
```

#### `balancing_spend_lines`
Individual costs on a job — materials, transport, tools, labour paid to subcontractors.
```sql
CREATE TABLE balancing_spend_lines (
    id               SERIAL PRIMARY KEY,
    balancing_job_id TEXT REFERENCES balancing_jobs(id) ON DELETE CASCADE,
    paid_by          TEXT NOT NULL,          -- Hillary | Dennis
    description      TEXT NOT NULL,
    amount           REAL NOT NULL,
    date             DATE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

`paid_by` records who physically spent the money (took it from their pocket). This matters for the settlement calculation.

#### `balancing_settlements`
Cash transfers between Hillary and Dennis to settle up after a job.
```sql
CREATE TABLE balancing_settlements (
    id               SERIAL PRIMARY KEY,
    balancing_job_id TEXT REFERENCES balancing_jobs(id) ON DELETE CASCADE,
    date             DATE NOT NULL,
    amount           REAL NOT NULL,
    from_person      TEXT DEFAULT 'Hillary', -- who is paying: Hillary | Dennis
    notes            TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

`from_person` makes settlements direction-aware. "Hillary → Dennis" means Hillary is paying Dennis what she owes him. "Dennis → Hillary" means Dennis is repaying Hillary.

#### `tasks`
Simple to-do list, optionally linked to a quotation.
```sql
CREATE TABLE tasks (
    id                   SERIAL PRIMARY KEY,
    title                TEXT NOT NULL,
    description          TEXT DEFAULT '',
    due_date             DATE,
    priority             TEXT DEFAULT 'Normal',  -- Low | Normal | High | Urgent
    status               TEXT DEFAULT 'Pending', -- Pending | In Progress | Done
    assigned_to          TEXT DEFAULT '',
    linked_quotation_id  TEXT REFERENCES quotations(id),
    notes                TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);
```

#### `settings`
Key-value store for app state that needs to persist between requests.
```sql
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Seed rows:
INSERT INTO settings VALUES ('qt_year', '2026') ON CONFLICT DO NOTHING;
INSERT INTO settings VALUES ('qt_counter', '0') ON CONFLICT DO NOTHING;
```

Used for quotation numbering: `qt_year` and `qt_counter` together generate sequential numbers like `QT-2026-103`. When the year changes, the counter resets to 1.

---

## 6. Table Relationships

```
catalog_items ──────────────────────────────── template_items
service_providers                                    │
                                                     │ (template_id)
                                              system_templates

quotations (core)
    │
    ├── quotation_items          (quotation_id, CASCADE delete)
    ├── payments                 (quotation_id, CASCADE delete) [legacy]
    ├── job_executions           (quotation_id, CASCADE delete)
    ├── receipts                 (quotation_id, optional link)
    ├── maintenance_records      (linked_quotation_id, SET NULL on delete)
    ├── balancing_jobs           (linked_quotation_id, optional link)
    └── tasks                    (linked_quotation_id, optional link)

balancing_jobs
    ├── balancing_spend_lines    (balancing_job_id, CASCADE delete)
    └── balancing_settlements    (balancing_job_id, CASCADE delete)

maintenance_records
    └── receipts                 (maintenance_id, optional link)
```

**Cascade delete:** When a parent row is deleted, PostgreSQL automatically deletes all child rows with `ON DELETE CASCADE`. This prevents orphaned records.

**SET NULL on delete:** `maintenance_records.linked_quotation_id` uses `ON DELETE SET NULL`. If you delete a quotation, the maintenance record remains but loses its quotation link. This is appropriate because maintenance records have independent value.

**Optional links (`quotation_id` on receipts):** A receipt can exist without a quotation link (standalone receipt). Optional foreign keys use `NULL` — not every receipt belongs to a quotation.

---

## 7. Module Reference

### Dashboard (`/`)

Runs 5 SQL queries in parallel (conceptually):
- Total quotation count
- Pending quotation count
- Outstanding balance (sum of `total_amount` minus sum of linked receipts, for non-cancelled jobs)
- Open maintenance count
- Tasks due within 3 days

Also shows:
- **Active Jobs** — quotations with status `Approved` or `In Progress`, with the most recent executor name from `job_executions` (via `DISTINCT ON`)
- **Overdue Tasks** — tasks past due date, not Done
- **Unbalanced Jobs** — completed quotations not yet in `balancing_jobs`

### Quotations (`/quotations`)

**List page:** Filterable by status and searchable by customer name / quotation number. Each row shows `payment_status` computed as:
```
paid = SUM(receipts.amount_paid) WHERE receipts.quotation_id = q.id
payment_status = "Paid" if paid >= total_amount else "Partial" if paid > 0 else "Unpaid"
```

**Form page (new + edit):** The line item table is a dynamic HTML table. Each row has `desc[]`, `uom[]`, `qty[]`, `price[]` as array-named inputs. On save, Flask reads them with `request.form.getlist("desc[]")` and zips them together.

**Quick Build (template loading):** Selecting a template calls `GET /api/template/<id>` via fetch. The API returns JSON. JavaScript clears the current rows and adds new ones from the JSON response. The template items are sorted client-side (Inverter → Battery → Panels → Other → Labour/Transport).

**VAT toggle:** A hidden input `apply-vat-hidden` tracks whether VAT is on. When "Add VAT" is clicked, it sets the value to `"1"` and shows the VAT rows. On save, Flask reads `apply_vat = f.get("apply_vat") == "1"`.

**Save logic (`_save_quotation`):** Uses PostgreSQL `ON CONFLICT (id) DO UPDATE` — this is an "upsert". The same function handles both create and edit. If the ID exists, it updates all fields. If not, it inserts.

**PDF:** Generated in memory by ReportLab (`utils/pdf.py`). Returned as a file download via `send_file(io.BytesIO(pdf_bytes), ...)`. No file is written to disk.

**Status changes:** A dedicated `POST /quotations/<qid>/status` route handles status updates. When set to `Completed`, a flash message with a link to create a maintenance record is shown.

### Receipts (`/receipts`)

Receipts are the single source of truth for all money received. There is no separate "customer payments" tracking in balancing — balancing reads receipts directly.

Key fields:
- `amount_fig` — the figure written on the receipt (what the customer is supposed to pay)
- `amount_paid` — actual cash received this transaction
- `balance` — `amount_fig - amount_paid` (how much is still outstanding on this receipt)
- `collected_by` — Hillary or Dennis (matters for balancing split)

Receipts can be pre-filled with `?qid=` (link from a quotation) or `?mid=` (link from a maintenance record).

### Maintenance (`/maintenance`)

Maintenance records track post-installation visits. Each record is independent — it is not a spend line on the original job's balancing.

**Type:**
- `Warranty` — free visit, Hillary absorbs the cost (no revenue expected)
- `Paid` — customer pays for the service call

**View page financial summary:** See [Section 9](#9-maintenance-pl--deep-dive).

### Catalog (`/catalog`)

54 items pre-seeded via `seed.sql`. Categories: Battery, Inverter, Solar Panel, Charge Controller, Cable, Accessory, Service. Items have `buy_price` (cost) and `sell_price` (what customer pays). The catalog picker on the quotation form lets you load a catalog item's sell price directly into a line item.

### Suppliers (`/suppliers`)

6 pre-seeded suppliers. Linked to catalog items via `catalog_items.supplier_id`. Text relationship — no hard foreign key constraint (to keep supplier deletion simple).

### Tasks (`/tasks`)

Sorted by `due_date ASC, priority DESC` (Urgent first within the same date). Color coding in the list:
- Red row — overdue (past due date)
- Yellow row — due within 3 days
- Normal — everything else

A "Done" quick-button on the list page saves a round-trip to the edit form.

---

## 8. Balancing — Deep Dive

Balancing tracks profit sharing after a job is completed. One `balancing_job` per installation.

### Data inputs

| Input | Source | Notes |
|-------|--------|-------|
| Quoted amount | `balancing_jobs.quoted` | Copied from the linked quotation |
| Spend lines | `balancing_spend_lines` | Each cost: description, amount, who paid |
| Customer receipts | `receipts` (via `quotation_id`) | Single source of truth — no separate table |
| Settlements | `balancing_settlements` | Cash transfers between Hillary and Dennis |
| Profit ratios | `balancing_jobs.h_ratio / d_ratio` | Default 45% / 55% |

### The math

```
total_costs         = SUM(spend_lines.amount)
dennis_spend        = SUM(spend_lines.amount WHERE paid_by = 'Dennis')
hillary_spend       = SUM(spend_lines.amount WHERE paid_by = 'Hillary')

profit              = quoted - total_costs

hillary_profit_share = profit × h_ratio / 100
dennis_profit_share  = profit × d_ratio / 100

hillary_total_due   = hillary_spend + hillary_profit_share
dennis_total_due    = dennis_spend  + dennis_profit_share
```

`total_due` answers: "How much money should this person end up with in their pocket after this job?"
- Their spend is returned to them (they fronted it from their own pocket)
- Plus their profit share

```
hillary_collected   = SUM(receipts.amount_paid WHERE collected_by = 'Hillary')
dennis_collected    = SUM(receipts.amount_paid WHERE collected_by = 'Dennis')

hillary_to_dennis   = SUM(settlements.amount WHERE from_person = 'Hillary')
dennis_to_hillary   = SUM(settlements.amount WHERE from_person = 'Dennis')
```

### Symmetric remaining formula

The remaining calculation must be symmetric — it accounts for the fact that whoever collected customer money has that money in their hand:

```
dennis_remaining  = dennis_total_due
                  - dennis_collected       (Dennis already has this from the customer)
                  - hillary_to_dennis      (Hillary already paid this to Dennis)
                  + dennis_to_hillary      (Dennis paid this back to Hillary, so it's back in the pool)

hillary_remaining = hillary_total_due
                  - hillary_collected      (Hillary already has this from the customer)
                  - dennis_to_hillary      (Dennis already paid this to Hillary)
                  + hillary_to_dennis      (Hillary paid this to Dennis, so it's gone from her pocket)
```

When `dennis_remaining <= 0`, Dennis has been fully paid. When `hillary_remaining <= 0`, Hillary's position is settled. Both ≤ 0 → status = `Settled`.

### Worked example

Job: Customer pays UGX 1,000,000. Dennis spent 200,000 on materials. Hillary spent 50,000 on transport.

```
total_costs         = 250,000
profit              = 1,000,000 - 250,000 = 750,000
hillary_profit_share = 750,000 × 45% = 337,500
dennis_profit_share  = 750,000 × 55% = 412,500
hillary_total_due   = 50,000 + 337,500 = 387,500
dennis_total_due    = 200,000 + 412,500 = 612,500
```

Customer pays Hillary: `hillary_collected = 1,000,000`

```
dennis_remaining    = 612,500 - 0 (dennis collected) - 0 (no settlements) + 0 = 612,500
hillary_remaining   = 387,500 - 1,000,000 (hillary collected) + 0 = -612,500
```

Hillary is -612,500 (she owes Dennis 612,500). Hillary records a settlement of 612,500 → Dennis.

```
After settlement:
dennis_remaining    = 612,500 - 0 - 612,500 + 0 = 0  ✓ Settled
hillary_remaining   = 387,500 - 1,000,000 + 612,500 = 0  ✓ Settled
```

### SQL: LATERAL join for receipts

Balancing cannot use a regular JOIN to sum receipts because each balancing job row needs to reference its own `linked_quotation_id` dynamically:

```sql
LEFT JOIN LATERAL (
    SELECT
        COALESCE(SUM(r.amount_paid), 0) AS total_collected,
        COALESCE(SUM(CASE WHEN r.collected_by='Hillary' THEN r.amount_paid ELSE 0 END), 0) AS hillary_collected,
        COALESCE(SUM(CASE WHEN r.collected_by='Dennis'  THEN r.amount_paid ELSE 0 END), 0) AS dennis_collected
    FROM receipts r
    WHERE r.quotation_id = j.linked_quotation_id   -- references outer query alias "j"
) cp ON true
```

`LATERAL` allows the subquery to reference columns from the outer query's current row (`j.linked_quotation_id`). Without `LATERAL`, a subquery is evaluated once and cannot reference the outer row.

---

## 9. Maintenance P&L — Deep Dive

Maintenance is a **separate P&L** from the original job balancing. It is not a spend line on the job.

### Why separate?

When a warranty visit happens, the job has already been balanced and closed. The maintenance cost is a new event. Adding it to the old balancing job would reopen a settled account.

### Financial model

```
total_cost  = parts_cost + labour_fee

revenue     = SUM(receipts.amount_paid WHERE maintenance_id = this_record)
              (0 for Warranty visits — no customer payment expected)

profit      = revenue - total_cost
              (negative for Warranty = a loss)

paid_by     = Hillary | Dennis (who fronted the cost from their pocket)

hillary_spend     = total_cost  if paid_by == 'Hillary'  else 0
dennis_spend      = total_cost  if paid_by == 'Dennis'   else 0

hillary_total_due = hillary_spend + profit × h_ratio / 100
dennis_total_due  = dennis_spend  + profit × d_ratio / 100

hillary_remaining = hillary_total_due - hillary_collected
dennis_remaining  = dennis_total_due  - dennis_collected
```

### Default ratios: 100/0

By default, `h_ratio = 100`, `d_ratio = 0`. This means Hillary bears 100% of maintenance costs and keeps 100% of maintenance revenue. Dennis is not involved.

To change: edit the maintenance record and adjust the ratio sliders. JavaScript keeps `h_ratio + d_ratio = 100`.

### Worked example — Warranty visit, Hillary paid

Visit cost: 80,000 (parts + labour). Type: Warranty (no revenue). Hillary paid.

```
total_cost          = 80,000
revenue             = 0
profit              = 0 - 80,000 = -80,000

At 100/0 (default):
hillary_spend       = 80,000
hillary_total_due   = 80,000 + (-80,000 × 100%) = 80,000 - 80,000 = 0
dennis_total_due    = 0 + (-80,000 × 0%) = 0

Both owe nothing. Hillary absorbed the full loss. Dennis is unaffected.
```

At 45/55 ratio:
```
hillary_total_due   = 80,000 + (-80,000 × 45%) = 80,000 - 36,000 = 44,000
dennis_total_due    = 0 + (-80,000 × 55%) = -44,000

dennis_remaining = -44,000 - 0 (dennis collected) = -44,000
→ "Dennis should pay Hillary UGX 44,000"
```

---

## 10. How Pages Are Served

### Server-side rendering (SSR)

Every page is fully rendered by the server. When you click a link or submit a form, the browser makes an HTTP request. The server runs Python, queries the database, fills a Jinja2 template, and returns complete HTML. The browser renders it.

**No client-side routing.** There is no single-page application (SPA). Each page load is a full HTTP round-trip.

### Static files

CSS, JavaScript, and images are served directly from the `static/` folder. In development, Flask serves them. In production, they go through Docker/Gunicorn (same process, but could be moved to a CDN for performance).

### JavaScript's role

JavaScript handles UI-only interactions that do not need a server round-trip:
- Column resizing (drag the column header border)
- Line item grand total calculation (updates as you type)
- VAT toggle (show/hide rows, recalculate)
- Drag-to-reorder line items
- Sidebar mobile toggle
- Template loading (one `fetch()` call to `/api/template/<id>`)

### The API endpoint

`GET /api/template/<id>` returns JSON. This is the only "API" endpoint — all other routes return HTML. Called by JavaScript when loading a Quick Build template.

### PDF generation

PDFs are generated in-memory (never saved to disk):
```python
pdf_bytes = build_quotation_pdf(q, items, sig_bytes)
return send_file(io.BytesIO(pdf_bytes), download_name="QT-2026-103.pdf",
                 as_attachment=True, mimetype="application/pdf")
```
`as_attachment=True` tells the browser to download rather than display.

### Flash messages

After a save/delete/update, the server redirects (POST → Redirect → GET pattern). This prevents duplicate form submissions on browser refresh. Before redirecting, it queues a flash message:
```python
flash("Quotation saved.", "success")
return redirect(url_for("quotations_view", qid=qid))
```
The next page reads the flash queue and displays it as a Bootstrap alert.

---

## 11. PWA Setup

The app is a Progressive Web App — installable on phone home screens.

### Files

- `static/manifest.json` — tells the browser the app name, colors, icon, and display mode
- `static/js/sw.js` — service worker (network-first caching strategy)
- `templates/base.html` — includes `<link rel="manifest">`, theme-color meta, and SW registration script

### Installing on iPhone (Safari)
1. Open `rincol-erp.onrender.com` in Safari
2. Tap the Share button (square with arrow)
3. Tap "Add to Home Screen"
4. Tap "Add"

### Installing on Android (Chrome)
1. Open the URL in Chrome
2. Chrome shows a banner "Add to Home Screen" automatically, or tap the three-dot menu → "Install app"

### Service worker strategy

Network-first: the app always tries to fetch from the network. If offline, it falls back to the cache. Static assets (CSS, JS) are cached after first load. HTML pages are not cached (always fresh from server).

---

## 12. File Structure

```
rincol-web/
├── app.py                   # All Flask routes and business logic (~1,100 lines)
├── schema.sql               # Initial PostgreSQL schema — run first in Supabase
├── migration.sql            # Schema upgrades — run second (idempotent)
├── seed.sql                 # Seed data: 54 catalog items, 6 suppliers, 7 templates
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container definition for deployment
├── fly.toml                 # Fly.io config (kept for reference; deployed on Render)
├── .env.example             # Copy to .env and fill in secrets
├── .gitignore
├── utils/
│   ├── __init__.py
│   ├── db.py                # psycopg2 connection pool, query/execute helpers
│   └── pdf.py               # ReportLab PDF builders (quotation + receipt)
├── static/
│   ├── manifest.json        # PWA web app manifest
│   ├── css/
│   │   └── style.css        # Dark theme, CSS variables, all component styles, mobile CSS
│   ├── js/
│   │   ├── main.js          # Column resize, line item editor, VAT toggle, drag-sort, sidebar
│   │   └── sw.js            # Service worker (network-first caching)
│   └── img/
│       ├── rincol_icon.png  # Square app icon (512×512) — used as favicon + PWA icon
│       ├── rincol_logo.png  # Full landscape logo — used in PDF letterhead fallback
│       ├── letterhead.png   # Full-width letterhead image for PDFs
│       └── signature.png    # Hillary's signature — auto-included in PDFs
└── templates/
    ├── base.html            # Master layout: sidebar, topbar, flash messages, scripts
    ├── dashboard.html
    ├── auth/
    │   └── login.html
    ├── quotation/
    │   ├── list.html        # Searchable/filterable list with status badges
    │   ├── form.html        # Line item editor, Quick Build, VAT toggle, drag-to-reorder
    │   └── view.html        # Payments, job execution, VAT breakdown, PDF link
    ├── receipt/
    │   ├── list.html
    │   ├── form.html        # Optional quotation/maintenance link, balance auto-calc
    │   └── view.html
    ├── maintenance/
    │   ├── list.html
    │   ├── form.html        # Linked quotation auto-fill, cost split sliders
    │   └── view.html        # Financial summary, per-person P&L, settlement direction
    ├── catalog/
    │   ├── list.html
    │   └── form.html
    ├── suppliers/
    │   ├── list.html
    │   └── form.html
    ├── balancing/
    │   ├── list.html        # Summary strip (total profit, per-person remaining)
    │   ├── form.html        # Job creation / edit with spend line editor
    │   ├── view.html        # Spend lines, receipts (read-only), settlements, financial breakdown
    │   └── report.html      # Company-wide profit report across all jobs
    └── tasks/
        ├── list.html        # Color-coded by urgency, quick Done button
        └── form.html
```

---

## 13. Local Development

### Prerequisites

- Python 3.11 or 3.12
- A Supabase project (free tier works — one project per account)
- Git

### Step-by-step setup

```bash
# 1. Clone the repo
git clone https://github.com/arindakhill/rincol-erp.git
cd rincol-erp

# 2. Create virtual environment and activate it
python3 -m venv .venv
source .venv/bin/activate     # Mac/Linux
# .venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env
# Now open .env and fill in the values (see Section 15)

# 5. Set up the database
# Go to your Supabase project → SQL Editor
# Run schema.sql  (copy-paste the whole file)
# Run migration.sql (copy-paste the whole file)
# Run seed.sql  (copy-paste the whole file)

# 6. Create users in Supabase
# Supabase Dashboard → Authentication → Users → "Invite user"
# Create: hillary@rincol.com and dennis@rincol.com
# In user_metadata, add: {"full_name": "Hillary Arinda"}
# After creating, use "Send password recovery" to let them set their own password

# 7. Run the app
python app.py
# Open http://localhost:5000
```

### Database URL for local dev

Use the **Session pooler** URL from Supabase → Connect → Session pooler. This works from any network.

Format:
```
postgresql://postgres.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres
```

Do NOT use the direct connection URL (`db.xxx.supabase.co:5432`) — it uses IPv6 and may not work from all networks.

### Re-running migrations safely

All SQL statements in `schema.sql` and `migration.sql` use `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`. They are safe to re-run without duplicating data or errors.

---

## 14. Cloud Deployment (Render)

The app is hosted on Render's free tier. Render detects the `Dockerfile` and builds a container.

### First deployment

```bash
# Install GitHub CLI
brew install gh

# Login to GitHub
gh auth login

# Create private repo and push
cd rincol-erp
git init
git add .
git commit -m "Initial commit"
gh repo create rincol-erp --private --source=. --push
```

Then in Render:
1. Go to render.com → New → Web Service
2. Connect your GitHub repo (`rincol-erp`)
3. Render detects Docker automatically
4. Select **Free** instance type
5. Add environment variables (Section 15)
6. Click Deploy

### Subsequent deploys

Every `git push` to `main` triggers an automatic redeploy on Render.

```bash
git add .
git commit -m "describe your change"
git push
```

### Free tier caveats

- The app **spins down after 15 minutes of inactivity**. The first request after inactivity takes 30-60 seconds to wake up.
- To avoid this: upgrade to the $7/month Starter plan (always-on)
- Or use UptimeRobot (free) to ping the URL every 10 minutes and keep it awake

### Environment variables on Render

Go to Render → rincol-erp → Environment → add each variable manually. Changes take effect on next deploy.

---

## 15. Environment Variables

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `FLASK_SECRET_KEY` | Yes | Any long random string (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `SUPABASE_URL` | Yes | Supabase → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase → Project Settings → API → anon/public key |
| `DATABASE_URL` | Yes | Supabase → Connect → Session pooler → Connection string |

**Never commit `.env` to git.** It is in `.gitignore`. Use `.env.example` to document which variables exist.

---

## 16. Key Design Decisions

### No ORM — raw SQL only

SQLAlchemy or Django ORM would abstract the database. This app uses raw psycopg2 for full SQL control: LATERAL joins, DISTINCT ON, ON CONFLICT upserts, window functions. The helper functions (`query`, `query_one`, `execute`) are thin wrappers that handle cursors and parameter binding.

### Server-side rendering — no JavaScript framework

No build step, no `node_modules`, no bundler. Bootstrap 5 and Bootstrap Icons are loaded from CDN. All interactivity is vanilla JavaScript (~600 lines total). This makes the codebase easy to understand and deploy.

### Receipts as single source of truth

There is no separate "customer payments" table in balancing. `balancing_customer_payments` existed briefly but was removed. Receipts (with `quotation_id`) are the authoritative record of money received. Balancing reads from `receipts` via a LATERAL join. This eliminates double-entry.

### Upsert pattern for saves

`INSERT ... ON CONFLICT (id) DO UPDATE SET ...` handles both create and edit in one SQL statement. The same `_save_quotation()` function is called by both `quotations_new()` and `quotations_edit()`.

### Maintenance is post-balancing

Maintenance visits happen after a job is completed and balanced. They are not spend lines on the original balancing job — they are an independent mini P&L. This reflects the real business workflow: the job is closed, and maintenance is a new financial event.

### Sequential quotation numbers with DB-backed counter

`settings` table stores `qt_year` and `qt_counter`. `next_quotation_number()` reads both, increments the counter, and commits immediately (not as part of the request transaction). This ensures numbers are never reused even if the request fails after number generation.

### Connection pool resilience

`utils/db.py` uses a `ThreadedConnectionPool` (min 1, max 5 connections). The session pooler can close idle connections. `_fresh_conn()` validates every connection with `conn.reset()` before returning it. Dead connections are discarded and replaced. `close_db()` catches `InterfaceError` gracefully.

### PWA for mobile

The app is installable on iPhone and Android as a home screen app via standard Web App Manifest + Service Worker. No React Native, no Expo, no app store. The same codebase runs on desktop and mobile.
