-- Catalog spec_data migration — run in Supabase SQL Editor
-- Safe to re-run: uses ADD COLUMN IF NOT EXISTS

-- Add structured electrical specs column to catalog_items
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS spec_data JSONB DEFAULT '{}';

-- Add battery_is_bank flag to solar_sizings
-- (battery spec represents a complete voltage bank — no series connection)
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS battery_is_bank BOOLEAN DEFAULT FALSE;
