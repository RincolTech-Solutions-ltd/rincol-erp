-- Rincol Web ERP — Schema Migration
-- Run this in Supabase SQL Editor AFTER the initial schema.sql has been applied.
-- Safe to re-run: all statements use IF NOT EXISTS / ON CONFLICT.

-- ── 1. Link receipts to quotations (optional) ────────────────────────────────
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS quotation_id TEXT REFERENCES quotations(id);

-- ── 2. Upgrade balancing_jobs ────────────────────────────────────────────────
ALTER TABLE balancing_jobs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Open';
ALTER TABLE balancing_jobs ADD COLUMN IF NOT EXISTS linked_quotation_id TEXT REFERENCES quotations(id);
-- Fix default ratios to Dennis 55% / Hillary 45%
ALTER TABLE balancing_jobs ALTER COLUMN h_ratio SET DEFAULT 45;
ALTER TABLE balancing_jobs ALTER COLUMN d_ratio SET DEFAULT 55;

-- ── 3. Balancing spend lines (individual purchases/labour, with who paid) ────
CREATE TABLE IF NOT EXISTS balancing_spend_lines (
    id SERIAL PRIMARY KEY,
    balancing_job_id TEXT REFERENCES balancing_jobs(id) ON DELETE CASCADE,
    paid_by TEXT NOT NULL,       -- Hillary | Dennis
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bal_spend_job ON balancing_spend_lines(balancing_job_id);

-- ── 4. Customer payments per balancing job (who collected, when, how much) ───
CREATE TABLE IF NOT EXISTS balancing_customer_payments (
    id SERIAL PRIMARY KEY,
    balancing_job_id TEXT REFERENCES balancing_jobs(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    amount REAL NOT NULL,
    received_by TEXT NOT NULL,   -- Hillary | Dennis
    method TEXT DEFAULT 'Cash',  -- Cash | MM | EFT
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bal_cpay_job ON balancing_customer_payments(balancing_job_id);

-- ── 5. Settlements (Hillary paying Dennis his total due) ─────────────────────
CREATE TABLE IF NOT EXISTS balancing_settlements (
    id SERIAL PRIMARY KEY,
    balancing_job_id TEXT REFERENCES balancing_jobs(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    amount REAL NOT NULL,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bal_settle_job ON balancing_settlements(balancing_job_id);

-- ── 6. Tasks / To-Do list ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date DATE,
    priority TEXT DEFAULT 'Normal',  -- Low | Normal | High | Urgent
    status TEXT DEFAULT 'Pending',   -- Pending | In Progress | Done
    assigned_to TEXT DEFAULT '',
    linked_quotation_id TEXT REFERENCES quotations(id),
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);

-- ── 7. Who collected payment on each receipt ─────────────────────────────────
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS collected_by TEXT DEFAULT 'Hillary';

-- ── 8. Symmetric settlement direction (Hillary→Dennis or Dennis→Hillary) ─────
ALTER TABLE balancing_settlements ADD COLUMN IF NOT EXISTS from_person TEXT DEFAULT 'Hillary';
