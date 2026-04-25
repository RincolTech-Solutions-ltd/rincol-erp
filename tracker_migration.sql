-- MPPT tracker parameters migration — run in Supabase SQL Editor
-- Safe to re-run: all ADD COLUMN IF NOT EXISTS

-- Panel Isc (for string current calculations and DC CB sizing)
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS panel_isc REAL DEFAULT 0;

-- Inverter MPPT range (replaces hardcoded MIN_INVERTER_INPUT_V = 120)
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS mppt_trackers INTEGER DEFAULT 1;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS mppt_min_v REAL DEFAULT 0;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS mppt_max_v REAL DEFAULT 0;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS max_oc_v REAL DEFAULT 0;

-- Tracker current and power limits
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS max_input_current_per_tracker REAL DEFAULT 0;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS max_isc_per_tracker REAL DEFAULT 0;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS max_pv_power_per_tracker REAL DEFAULT 0;

-- Computed panel array results
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS panels_in_series INTEGER DEFAULT 1;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS strings_total INTEGER DEFAULT 1;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS strings_per_tracker INTEGER DEFAULT 1;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS panel_array_flag TEXT DEFAULT '';
