-- BoM override feature: lock flag so user edits survive sizing re-saves
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS bom_locked BOOLEAN DEFAULT FALSE;
