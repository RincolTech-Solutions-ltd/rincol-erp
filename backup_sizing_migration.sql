-- Backup Sizing Module — run in Supabase SQL Editor AFTER schema.sql
-- Also run srne_catalog_migration.sql to seed inverters and batteries

CREATE TABLE IF NOT EXISTS backup_sizing (
    id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    quotation_id        TEXT REFERENCES quotations(id) ON DELETE SET NULL,
    site_ref            TEXT,
    customer_name       TEXT,
    load_items          JSONB NOT NULL DEFAULT '[]',
    backup_hours        NUMERIC NOT NULL DEFAULT 4,
    dod                 NUMERIC NOT NULL DEFAULT 0.80,
    inverter_efficiency NUMERIC NOT NULL DEFAULT 0.90,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backup_sizing_quotation ON backup_sizing(quotation_id);
CREATE INDEX IF NOT EXISTS idx_backup_sizing_created  ON backup_sizing(created_at DESC);
