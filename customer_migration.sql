-- ─────────────────────────────────────────────────────────────────────────────
-- Rincol Web ERP — Customer Module Migration
-- Run in Supabase SQL Editor in order. Safe to re-run (all IF NOT EXISTS).
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Step 1: Sequence for customer_no (CUST-0001, CUST-0002 ...) ───────────────
CREATE SEQUENCE IF NOT EXISTS customer_no_seq START 1;

-- ── Step 2: Customers table ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id               UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_no      TEXT  UNIQUE NOT NULL,
    name             TEXT  NOT NULL,
    phone            TEXT  DEFAULT '',
    email            TEXT  DEFAULT '',
    address          TEXT  DEFAULT '',
    statement_token  UUID  UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    notes            TEXT  DEFAULT '',          -- internal only, never shown to customer
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── Step 3: Link columns on existing tables ───────────────────────────────────
ALTER TABLE quotations
    ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL;

ALTER TABLE receipts
    ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL;

-- ── Step 4: Indexes ───────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_customers_phone           ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_customers_statement_token ON customers(statement_token);
CREATE INDEX IF NOT EXISTS idx_quotations_customer_id    ON quotations(customer_id);
CREATE INDEX IF NOT EXISTS idx_receipts_customer_id      ON receipts(customer_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 5: Data migration — extract unique customers from existing quotations
--
-- Dedup key: phone number (if not empty), otherwise customer name.
-- For each group we take the most recent name, email, and address
-- (in case any was updated on a later quotation).
-- customer_no is assigned in chronological order (first quotation = lowest number).
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO customers (id, customer_no, name, phone, email, address, statement_token, created_at)
SELECT
    gen_random_uuid(),
    'CUST-' || LPAD(nextval('customer_no_seq')::TEXT, 4, '0'),
    -- most recent name for this group
    (ARRAY_AGG(customer_name     ORDER BY created_at DESC))[1],
    -- phone (empty string for phone-less groups)
    COALESCE(MAX(NULLIF(customer_phone,   '')), ''),
    -- most recent non-empty email
    COALESCE((ARRAY_AGG(NULLIF(customer_email,   '') ORDER BY created_at DESC))[1], ''),
    -- most recent non-empty address
    COALESCE((ARRAY_AGG(NULLIF(customer_address, '') ORDER BY created_at DESC))[1], ''),
    gen_random_uuid(),
    MIN(created_at)
FROM quotations
GROUP BY
    -- group by phone if present, otherwise by name
    CASE
        WHEN customer_phone != '' THEN customer_phone
        ELSE customer_name
    END
ORDER BY MIN(created_at);  -- chronological → lowest CUST numbers to oldest customers

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 6: Link existing quotations → customers
-- Match on phone first; fall back to name for phone-less records.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE quotations q
SET    customer_id = c.id
FROM   customers c
WHERE  q.customer_id IS NULL
  AND (
        (q.customer_phone != '' AND q.customer_phone = c.phone)
     OR (q.customer_phone  = '' AND q.customer_name  = c.name)
      );

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 7: Link existing receipts → customers (same logic)
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE receipts r
SET    customer_id = c.id
FROM   customers c
WHERE  r.customer_id IS NULL
  AND (
        (r.customer_phone != '' AND r.customer_phone = c.phone)
     OR (r.customer_phone  = '' AND r.customer_name  = c.name)
      );

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification queries — run these after the migration to sanity-check
-- ─────────────────────────────────────────────────────────────────────────────
-- SELECT COUNT(*) FROM customers;                          -- should be > 0
-- SELECT customer_no, name, phone FROM customers ORDER BY customer_no;
-- SELECT COUNT(*) FROM quotations WHERE customer_id IS NULL;  -- ideally 0
-- SELECT COUNT(*) FROM receipts   WHERE customer_id IS NULL;  -- ideally 0
