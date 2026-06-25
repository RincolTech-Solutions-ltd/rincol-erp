-- Add customer_id FK to backup_sizing — run in Supabase SQL Editor
ALTER TABLE backup_sizing
    ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL;
