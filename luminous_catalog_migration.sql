-- Luminous Catalog Seeding — run in Supabase SQL Editor
-- Source: Luminous Uganda pricelist (photo)
-- Sell price = buy price x 1.20 (20% margin)
-- X-marked and O/S items excluded

-- ── Supplier ──────────────────────────────────────────────────────────────────
INSERT INTO service_providers (id, name, contact_person, phone, email, location, categories, notes)
VALUES ('SUP-008', 'Luminous (Uganda)', '', '', '', 'Kampala', 'Inverter,Battery,Solar Panel',
        'Luminous hybrid inverters, tubular and Li-Ion batteries, solar panels.')
ON CONFLICT (id) DO NOTHING;

-- ── Hybrid Inverters ──────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('INV-LUM-001', 'Inverter', 'Hybrid Inverter 850VA/12V',
   '850VA / 12V', 'pc', 280000, 336000, 'SUP-008',
   'Hybrid inverter-charger. 12V battery bus.',
   '{"battery_voltage": 12, "inverter_kw": 0.85, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-002', 'Inverter', 'Hybrid Inverter 1150VA/12V',
   '1150VA / 12V', 'pc', 350000, 420000, 'SUP-008',
   'Hybrid inverter-charger. 12V battery bus.',
   '{"battery_voltage": 12, "inverter_kw": 1.15, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-003', 'Inverter', 'Hybrid Inverter 1600VA/24V',
   '1600VA / 24V', 'pc', 380000, 456000, 'SUP-008',
   'Hybrid inverter-charger. 24V battery bus.',
   '{"battery_voltage": 24, "inverter_kw": 1.6, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-004', 'Inverter', 'Hybrid Inverter 2kW/24V',
   '2kW / 24V', 'pc', 550000, 660000, 'SUP-008',
   'Hybrid inverter-charger. 24V battery bus.',
   '{"battery_voltage": 24, "inverter_kw": 2.0, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-005', 'Inverter', 'Hybrid Inverter 3.5kW/24V',
   '3.5kW / 24V', 'pc', 1300000, 1560000, 'SUP-008',
   'Hybrid inverter-charger. 24V battery bus.',
   '{"battery_voltage": 24, "inverter_kw": 3.5, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-006', 'Inverter', 'Hybrid Inverter 4kW/24V',
   '4kW / 24V', 'pc', 1400000, 1680000, 'SUP-008',
   'Hybrid inverter-charger. 24V battery bus.',
   '{"battery_voltage": 24, "inverter_kw": 4.0, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-007', 'Inverter', 'Hybrid Inverter 6kW/48V',
   '6kW / 48V', 'pc', 1600000, 1920000, 'SUP-008',
   'Hybrid inverter-charger. 48V battery bus.',
   '{"battery_voltage": 48, "inverter_kw": 6.0, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-008', 'Inverter', 'Hybrid Inverter 8kW/48V',
   '8kW / 48V', 'pc', 3500000, 4200000, 'SUP-008',
   'Hybrid inverter-charger. 48V battery bus.',
   '{"battery_voltage": 48, "inverter_kw": 8.0, "controller_type": "MPPT"}'::jsonb),

  ('INV-LUM-009', 'Inverter', 'Hybrid Inverter 11kW/48V',
   '11kW / 48V', 'pc', 4000000, 4800000, 'SUP-008',
   'Hybrid inverter-charger. 48V battery bus.',
   '{"battery_voltage": 48, "inverter_kw": 11.0, "controller_type": "MPPT"}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- ── Batteries ─────────────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('BAT-LUM-001', 'Battery', 'LiFePO4 Battery 230Ah/51.2V',
   '51.2V / 230Ah / 11.78kWh', 'pc', 6000000, 7200000, 'SUP-008',
   'Li-Ion 48V bus. ~11.78kWh usable.',
   '{"ah": 230, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 8}'::jsonb),

  ('BAT-LUM-002', 'Battery', 'LiFePO4 Battery 230Ah/25.2V',
   '25.2V / 230Ah / 5.80kWh', 'pc', 3000000, 3600000, 'SUP-008',
   'Li-Ion 24V bus. ~5.80kWh usable.',
   '{"ah": 230, "voltage": 25.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 8}'::jsonb),

  ('BAT-LUM-003', 'Battery', 'Tubular Battery 150Ah/12V',
   '12V / 150Ah — Tubular', 'pc', 550000, 660000, 'SUP-008',
   'Lead-acid tubular. 50% recommended DoD.',
   '{"ah": 150, "voltage": 12.0, "dod_rated": 0.5, "chemistry": "Tubular", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-LUM-004', 'Battery', 'Tubular Battery 100Ah/12V',
   '12V / 100Ah — Tubular', 'pc', 350000, 420000, 'SUP-008',
   'Lead-acid tubular. 50% recommended DoD.',
   '{"ah": 100, "voltage": 12.0, "dod_rated": 0.5, "chemistry": "Tubular", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-LUM-005', 'Battery', 'Deep Cycle Battery 100Ah/12V',
   '12V / 100Ah — Deep Cycle', 'pc', 400000, 480000, 'SUP-008',
   'Lead-acid deep cycle. 50% recommended DoD.',
   '{"ah": 100, "voltage": 12.0, "dod_rated": 0.5, "chemistry": "Sealed Lead-Acid", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-LUM-006', 'Battery', 'LiFePO4 Battery 200Ah/12.8V',
   '12.8V / 200Ah / 2.56kWh', 'pc', 900000, 1080000, 'SUP-008',
   'Li-Ion 12V bus. ~2.56kWh usable.',
   '{"ah": 200, "voltage": 12.8, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-LUM-007', 'Battery', 'Gel Battery 200Ah/12V',
   '12V / 200Ah — Gel', 'pc', 800000, 960000, 'SUP-008',
   'Lead-acid gel. 50% recommended DoD.',
   '{"ah": 200, "voltage": 12.0, "dod_rated": 0.5, "chemistry": "Gel", "is_complete_bank": true, "max_parallel": 4}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- ── Solar Panel ───────────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('SOL-LUM-001', 'Solar Panel', 'Monocrystalline Panel 550Wp',
   '550W, Mono', 'pc', 350000, 420000, 'SUP-008',
   'Monocrystalline 550Wp solar panel.',
   '{"wp": 550}'::jsonb)

ON CONFLICT (id) DO NOTHING;
