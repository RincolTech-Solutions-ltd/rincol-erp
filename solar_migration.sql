-- Solar Sizing Module — Additive Migration
-- Run in Supabase SQL Editor (safe to re-run — all IF NOT EXISTS / ADD COLUMN IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS solar_sizings (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Client
    client_name TEXT NOT NULL,
    client_phone TEXT DEFAULT '',
    client_email TEXT DEFAULT '',
    client_site TEXT DEFAULT '',

    -- Utility / financial inputs
    utility_provider TEXT DEFAULT 'UEDCL',
    utility_tariff REAL DEFAULT 897,        -- UGX/kWh for 10-yr savings (full tariff incl. VAT)
    payback_tariff REAL DEFAULT 882,        -- UGX/kWh fixed benchmark for payback period
    tariff_escalation REAL DEFAULT 4.0,    -- % per year compound escalation (ERA Uganda CAGR ~4%/yr 2015-2025)

    -- System parameters
    system_voltage INTEGER DEFAULT 48,      -- 12 or 48
    battery_type TEXT DEFAULT 'Li-ion',     -- Li-ion | Lead Acid
    days_autonomy INTEGER DEFAULT 1,
    dod REAL DEFAULT 0.80,                  -- 0.80 applies to both Li-ion and Eastman tubular gel
    inverter_efficiency REAL DEFAULT 0.90,
    cable_efficiency REAL DEFAULT 0.95,
    inverter_idle_w REAL DEFAULT 50,        -- inverter no-load draw (W), added to daily Wh before battery sizing
    peak_sun_hours REAL DEFAULT 5.5,
    performance_ratio REAL DEFAULT 0.75,

    -- Equipment specs (per unit)
    panel_wp REAL DEFAULT 550,
    panel_voc REAL DEFAULT 40.0,
    panel_cost REAL DEFAULT 0,              -- UGX per panel
    battery_ah REAL DEFAULT 200,
    battery_voltage REAL DEFAULT 12,        -- voltage per battery unit
    battery_cost_each REAL DEFAULT 0,       -- UGX per battery
    inverter_kw REAL DEFAULT 3.5,
    inverter_cost REAL DEFAULT 0,
    labour_transport REAL DEFAULT 750000,

    -- Calculated results (stored after save/calculate)
    total_daily_wh REAL DEFAULT 0,          -- includes inverter idle draw
    inverter_idle_wh REAL DEFAULT 0,        -- for display: how much idle draw adds
    peak_load_w REAL DEFAULT 0,
    battery_ah_min REAL DEFAULT 0,
    batteries_in_series INTEGER DEFAULT 1,
    batteries_in_parallel INTEGER DEFAULT 1,
    total_batteries INTEGER DEFAULT 1,
    required_wp REAL DEFAULT 0,
    panels_by_energy INTEGER DEFAULT 1,
    panels_by_voltage INTEGER DEFAULT 0,
    panels_recommended INTEGER DEFAULT 1,
    voltage_override BOOLEAN DEFAULT false,
    annual_yield_kwh REAL DEFAULT 0,
    system_cost REAL DEFAULT 0,
    maintenance_cost_10yr REAL DEFAULT 0,
    solar_cost_per_kwh REAL DEFAULT 0,
    yaka_savings_10yr REAL DEFAULT 0,
    payback_years REAL DEFAULT 0,
    inverter_flag TEXT DEFAULT '',

    -- Linked quotation (after "Send to Quotation")
    quotation_id TEXT REFERENCES quotations(id) ON DELETE SET NULL,

    notes TEXT DEFAULT '',
    status TEXT DEFAULT 'Draft'             -- Draft | Sent | Archived
);

CREATE TABLE IF NOT EXISTS solar_sizing_appliances (
    id SERIAL PRIMARY KEY,
    sizing_id TEXT REFERENCES solar_sizings(id) ON DELETE CASCADE,
    line_no INTEGER DEFAULT 0,
    name TEXT NOT NULL,
    load_type TEXT DEFAULT 'standard',      -- standard | fridge
    power_w REAL DEFAULT 0,                 -- for standard: rated watts; for fridge: compressor/startup watts (peak demand only)
    power_factor REAL DEFAULT 1.0,
    quantity INTEGER DEFAULT 1,
    hours_per_day REAL DEFAULT 0,           -- for standard loads
    annual_kwh REAL DEFAULT 0,              -- for fridges: kWh/year from energy label ÷ 365 = daily Wh
    peak_w REAL DEFAULT 0,                  -- for fridges: startup/compressor peak watts (inverter sizing)
    included BOOLEAN DEFAULT true,
    daily_wh REAL DEFAULT 0               -- computed daily energy contribution
);

CREATE TABLE IF NOT EXISTS solar_sizing_bom (
    id SERIAL PRIMARY KEY,
    sizing_id TEXT REFERENCES solar_sizings(id) ON DELETE CASCADE,
    line_no INTEGER DEFAULT 0,
    description TEXT NOT NULL,
    uom TEXT DEFAULT 'pc',
    qty REAL DEFAULT 1,
    unit_price REAL DEFAULT 0,
    total REAL DEFAULT 0
);

-- If the tables already exist, add any missing columns (safe to re-run)
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS tariff_escalation REAL DEFAULT 4.0;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS inverter_idle_w REAL DEFAULT 50;
ALTER TABLE solar_sizings ADD COLUMN IF NOT EXISTS inverter_idle_wh REAL DEFAULT 0;
ALTER TABLE solar_sizing_appliances ADD COLUMN IF NOT EXISTS load_type TEXT DEFAULT 'standard';
ALTER TABLE solar_sizing_appliances ADD COLUMN IF NOT EXISTS annual_kwh REAL DEFAULT 0;
ALTER TABLE solar_sizing_appliances ADD COLUMN IF NOT EXISTS peak_w REAL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_solar_sizings_client ON solar_sizings(client_name);
CREATE INDEX IF NOT EXISTS idx_solar_sizings_status ON solar_sizings(status);
CREATE INDEX IF NOT EXISTS idx_solar_appliances_sizing ON solar_sizing_appliances(sizing_id);
CREATE INDEX IF NOT EXISTS idx_solar_bom_sizing ON solar_sizing_bom(sizing_id);
