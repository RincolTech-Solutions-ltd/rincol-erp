-- maintenance_cancel_migration.sql
-- Run in Supabase SQL editor

ALTER TABLE maintenance_records
  ADD COLUMN IF NOT EXISTS cancellation_reason TEXT DEFAULT '';
