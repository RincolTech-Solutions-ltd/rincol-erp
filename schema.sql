-- Rincol Web ERP — PostgreSQL Schema (Supabase)
-- Run this in Supabase SQL Editor after creating your project

-- ── Catalog ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS catalog_items (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    spec TEXT DEFAULT '',
    uom TEXT DEFAULT 'pc',
    buy_price INTEGER DEFAULT 0,
    sell_price INTEGER DEFAULT 0,
    supplier_id TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Suppliers ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS service_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    location TEXT DEFAULT '',
    categories TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── System Templates ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS template_items (
    id SERIAL PRIMARY KEY,
    template_id TEXT REFERENCES system_templates(id) ON DELETE CASCADE,
    catalog_item_id TEXT,
    description TEXT,
    uom TEXT DEFAULT 'pc',
    qty REAL DEFAULT 1
);

-- ── Quotations ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quotations (
    id TEXT PRIMARY KEY,
    quotation_no TEXT UNIQUE NOT NULL,
    date DATE NOT NULL,
    title TEXT DEFAULT 'Quotation',
    customer_name TEXT NOT NULL,
    customer_phone TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    customer_address TEXT DEFAULT '',
    delivery TEXT DEFAULT '1-2 days after 70% material cost payment',
    validity TEXT DEFAULT '30 days',
    warranty TEXT DEFAULT '12 months commencing on the delivery date',
    payment_terms TEXT DEFAULT 'Cash / MM / EFT',
    status TEXT DEFAULT 'Pending',  -- Pending / Approved / In Progress / Completed / Cancelled
    total_amount REAL DEFAULT 0,
    notes TEXT DEFAULT '',
    sig_issued_url TEXT DEFAULT '',   -- Supabase Storage URL for issued-by signature
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quotation_items (
    id SERIAL PRIMARY KEY,
    quotation_id TEXT REFERENCES quotations(id) ON DELETE CASCADE,
    line_no INTEGER NOT NULL,
    description TEXT NOT NULL,
    uom TEXT DEFAULT 'pc',
    qty REAL DEFAULT 1,
    unit_price REAL DEFAULT 0,
    total REAL DEFAULT 0
);

-- ── Payment Records ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    quotation_id TEXT REFERENCES quotations(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    amount REAL NOT NULL,
    method TEXT DEFAULT 'Cash',   -- Cash / MM / EFT
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Job Execution ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_executions (
    id SERIAL PRIMARY KEY,
    quotation_id TEXT REFERENCES quotations(id) ON DELETE CASCADE,
    executor_name TEXT NOT NULL,
    executor_payment REAL DEFAULT 0,
    execution_date DATE,
    notes TEXT DEFAULT ''
);

-- ── Maintenance Records ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maintenance_records (
    id SERIAL PRIMARY KEY,
    linked_quotation_id TEXT REFERENCES quotations(id) ON DELETE SET NULL,
    client_name TEXT NOT NULL,
    client_phone TEXT DEFAULT '',
    visit_date DATE NOT NULL,
    type TEXT DEFAULT 'Paid',   -- Warranty / Paid
    problem TEXT DEFAULT '',
    parts_used TEXT DEFAULT '',
    parts_cost REAL DEFAULT 0,
    labour_fee REAL DEFAULT 0,
    executor_name TEXT DEFAULT '',
    executor_payment REAL DEFAULT 0,
    status TEXT DEFAULT 'Open',   -- Open / Resolved / Pending Parts
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Balancing Jobs ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balancing_jobs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    quotation_ref TEXT DEFAULT '',
    date DATE NOT NULL,
    quoted REAL DEFAULT 0,
    materials REAL DEFAULT 0,
    labour REAL DEFAULT 0,
    transport REAL DEFAULT 0,
    other_expenses REAL DEFAULT 0,
    h_ratio INTEGER DEFAULT 60,
    d_ratio INTEGER DEFAULT 40,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Settings ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO settings VALUES ('qt_year', EXTRACT(YEAR FROM NOW())::TEXT) ON CONFLICT DO NOTHING;
INSERT INTO settings VALUES ('qt_counter', '0') ON CONFLICT DO NOTHING;

-- ── Receipts ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    receipt_no TEXT UNIQUE NOT NULL,
    date DATE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    customer_address TEXT DEFAULT '',
    being_for TEXT DEFAULT '',
    amount_fig REAL DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    cheque_no TEXT DEFAULT '',
    issued_name TEXT DEFAULT '',
    received_name TEXT DEFAULT '',
    sig_issued_url TEXT DEFAULT '',
    sig_received_url TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_quotations_status ON quotations(status);
CREATE INDEX IF NOT EXISTS idx_quotations_customer ON quotations(customer_name);
CREATE INDEX IF NOT EXISTS idx_payments_quotation ON payments(quotation_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_status ON maintenance_records(status);
CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog_items(category);
