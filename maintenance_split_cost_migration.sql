-- maintenance_split_cost_migration.sql
-- ONE-SHOT: already applied to production Hetzner Postgres on 2026-09-22.
-- Do not re-run against prod without re-checking the WHERE clause below
-- first (see the idempotency note on the backfill UPDATE).
--
-- Adds an external-service cost category and lets both Hillary and Dennis
-- front part of a job's cost, replacing the single paid_by dropdown
-- (which only allowed one person to have fronted 100%).

ALTER TABLE maintenance_records
  ADD COLUMN IF NOT EXISTS external_cost      REAL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS external_cost_desc TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS hillary_paid       REAL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dennis_paid        REAL DEFAULT 0;

-- Backfill existing rows from the old single-payer paid_by field, so
-- historical records keep the same total cost attribution they had before.
-- Scoped to rows that existed when this actually ran (2026-09-22 ~05:30 UTC),
-- so a later legitimate 0/0 row (a genuinely free job, or attribution cleared
-- on purpose) can never be silently resurrected by an accidental re-run, while
-- still reproducing the real production state if replayed on a restored backup.
UPDATE maintenance_records
SET hillary_paid = CASE WHEN paid_by = 'Hillary' THEN COALESCE(parts_cost,0) + COALESCE(labour_fee,0) ELSE 0 END,
    dennis_paid  = CASE WHEN paid_by = 'Dennis'  THEN COALESCE(parts_cost,0) + COALESCE(labour_fee,0) ELSE 0 END
WHERE hillary_paid = 0 AND dennis_paid = 0
  AND created_at < '2026-09-22 05:30:00+00';
