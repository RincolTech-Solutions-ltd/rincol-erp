-- Add customer FK to solar_sizings — run in Supabase SQL Editor
ALTER TABLE solar_sizings
    ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) ON DELETE SET NULL;
