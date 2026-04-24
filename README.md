# Rincol Web ERP

Internal business management system for Rincol Tech Solutions. Built with Flask + Supabase.

**Users:** Hillary Arinda (admin), Dennis Kaweesi (field)
**Deployment:** Fly.io (`rincol-erp`, `jnb` region)
**Stack:** Python 3.12 / Flask · Supabase (PostgreSQL + Auth) · Bootstrap 5 (dark) · Vanilla JS · Gunicorn

---

## Modules

| Module | URL | Purpose |
|---|---|---|
| Dashboard | `/` | Summary stats, recent quotations, overdue tasks |
| Quotations | `/quotations` | Full quotation lifecycle — create, edit, PDF, payments, job execution |
| Receipts | `/receipts` | Standalone receipts, optionally linked to a quotation |
| Maintenance | `/maintenance` | Service/warranty visits, linked to quotations, cost tracking |
| Catalog | `/catalog` | 54 items across 7 categories with buy/sell prices |
| Suppliers | `/suppliers` | 6 pre-seeded service providers |
| Balancing | `/balancing` | Per-job profit tracking, spend lines, settlements between Hillary and Dennis |
| Tasks | `/tasks` | To-do list with due dates, priority, overdue alerts |

---

## Quotation Statuses

Two independent statuses per quotation:

**Job Status** (work lifecycle):
- `Pending` — created, not yet approved
- `Approved` — customer confirmed, not started
- `In Progress` — actively being executed
- `Completed` — work done
- `Cancelled` — not proceeding

**Payment Status** (computed, not stored — derived from payments table):
- `Unpaid` — no payments recorded
- `Partial` — some payments, balance > 0
- `Paid` — sum of payments >= total amount

---

## Balancing Logic

Tracks profit sharing between Hillary (45%) and Dennis (55%) per job.

```
Profit = Quoted Amount − Σ Spend Lines
Hillary profit share = Profit × 45%
Dennis profit share  = Profit × 55%
Dennis total due     = Dennis spend + Dennis profit share
Dennis remaining     = Dennis total due − Dennis collected − Hillary settlements
```

**Spend lines** — each cost recorded with who paid it (Hillary or Dennis).
**Customer payments** — who received money from the customer.
**Settlements** — Hillary paying Dennis his total due.

Warranty maintenance costs (from linked quotation's Warranty maintenance records) are shown as a deduction from true profit in the job view.

---

## File Structure

```
rincol-web/
├── app.py                  # All Flask routes
├── schema.sql              # Initial database schema (run first)
├── migration.sql           # Schema upgrades (run after schema.sql)
├── seed.sql                # Seed data: 54 catalog items, 6 suppliers, 7 templates
├── requirements.txt
├── Dockerfile
├── fly.toml                # Fly.io config (app: rincol-erp, region: jnb)
├── .env.example            # Copy to .env and fill in
├── utils/
│   ├── db.py               # psycopg2 helpers: query(), execute(), query_one()
│   └── pdf.py              # ReportLab PDF builders for quotations and receipts
├── static/
│   ├── css/style.css       # Dark theme (#1a1a2e), CSS variables, status badges
│   └── js/main.js          # Column resize, line-item editor, Quick Build loader, receipt balance
└── templates/
    ├── base.html           # Sidebar layout, Bootstrap 5, dark theme
    ├── dashboard.html
    ├── auth/login.html
    ├── quotation/
    │   ├── list.html       # Filter by status/search, dual status badges
    │   ├── form.html       # Line-item editor, resizable columns, Quick Build
    │   └── view.html       # Payments, execution records, PDF
    ├── receipt/
    │   ├── list.html
    │   ├── form.html       # Optional quotation link, balance auto-calc
    │   └── view.html
    ├── maintenance/
    │   ├── list.html
    │   └── form.html
    ├── catalog/
    │   ├── list.html
    │   └── form.html
    ├── suppliers/
    │   ├── list.html
    │   └── form.html
    ├── balancing/
    │   ├── list.html       # Summary strip, per-job figures
    │   ├── form.html       # Job creation / edit
    │   ├── view.html       # Spend lines, customer payments, settlements, snapshot
    │   └── report.html     # Company-wide profit report
    └── tasks/
        ├── list.html       # Overdue/due-soon row colors, quick Done button
        └── form.html
```

---

## Database Tables

| Table | Purpose |
|---|---|
| `quotations` | Quotation headers |
| `quotation_items` | Line items per quotation |
| `payments` | Customer payments against quotations |
| `job_executions` | Who executed the job, when, what they were paid |
| `receipts` | Standalone receipts (optionally linked to quotation) |
| `maintenance_records` | Service/warranty visits |
| `catalog_items` | Product/service catalog with buy/sell prices |
| `service_providers` | Suppliers |
| `system_templates` | Quick Build template headers |
| `template_items` | Lines per template |
| `balancing_jobs` | Per-job balancing records |
| `balancing_spend_lines` | Individual cost lines (paid by Hillary or Dennis) |
| `balancing_customer_payments` | Money received from customer per job |
| `balancing_settlements` | Hillary's payments to Dennis |
| `tasks` | To-do items with due dates and priority |
| `settings` | Key-value store (quotation counter, year) |

---

## Local Development

### Prerequisites
- Python 3.12+
- A Supabase project (free tier works)

### Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill environment file
cp .env.example .env
# Fill in: FLASK_SECRET_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, DATABASE_URL

# 4. In Supabase SQL Editor, run in order:
#    a) schema.sql
#    b) migration.sql
#    c) seed.sql

# 5. In Supabase > Authentication > Users, create:
#    hillary@rincol.com  (user_metadata: {"full_name": "Hillary Arinda"})
#    dennis@rincol.com   (user_metadata: {"full_name": "Dennis Kaweesi"})

# 6. Run
python app.py
# Open http://localhost:5000
```

### Environment Variables

| Variable | Where to find |
|---|---|
| `FLASK_SECRET_KEY` | Any long random string |
| `SUPABASE_URL` | Supabase > Project Settings > API > Project URL |
| `SUPABASE_ANON_KEY` | Supabase > Project Settings > API > anon/public key |
| `DATABASE_URL` | Supabase > Project Settings > Database > Connection string (URI) |

---

## Deployment (Fly.io)

```bash
# First deploy
flyctl launch   # uses fly.toml

# Subsequent deploys
flyctl deploy

# Set environment variables on Fly
flyctl secrets set FLASK_SECRET_KEY=... SUPABASE_URL=... SUPABASE_ANON_KEY=... DATABASE_URL=...
```

App is configured for `jnb` (Johannesburg) region, 256MB RAM, always-on (never sleeps).

---

## PDF Generation

PDFs are built with ReportLab in `utils/pdf.py`. Letterhead requires:
- `static/img/letterhead.png` — full-width letterhead image
- `static/img/rincol_logo.png` — logo (used as fallback)

Place these files before generating PDFs. The PDF builder falls back gracefully if the files are missing.

---

## Key Design Decisions

- **No frontend build step** — Bootstrap 5 and Bootstrap Icons loaded from CDN. Vanilla JS only.
- **Resizable columns** — implemented in ~30 lines of vanilla JS (no jQuery, no colResizable library).
- **Payment status is computed, not stored** — derived from the `payments` table at query time. No manual status updates needed.
- **Balancing ratios default to Dennis 55% / Hillary 45%** — adjustable per job.
- **Warranty maintenance costs flow into balancing** — when a maintenance record is type=Warranty and linked to a quotation, its costs appear as a deduction in the balancing job view, showing true profit.
- **Auth via Supabase Auth** — `supabase.auth.sign_in_with_password()` for login. DB queries use psycopg2 directly (not the Supabase Python client) for full SQL control.
