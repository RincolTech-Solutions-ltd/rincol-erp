-- receipt_migration.sql
-- Run in Supabase SQL editor

ALTER TABLE receipts
  ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'Cash';
