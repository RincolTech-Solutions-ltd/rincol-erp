-- SRNE Catalog Seeding — run in Supabase SQL Editor
-- Source: Wholesale-Uganda SRNE items price list 2026-05-27
-- Sell price = buy price x 1.20 (20% margin), adjust per item as needed
-- Note: no brand names in item names (rule: brand info stays in supplier + spec fields only)

-- ── Supplier ──────────────────────────────────────────────────────────────────
INSERT INTO service_providers (id, name, contact_person, phone, email, location, categories, notes)
VALUES ('SUP-007', 'SRNE Solar (Uganda Wholesale)', '', '', '', 'Kampala', 'Inverter,Battery,Charge Controller,Solar Panel',
        'SRNE branded inverter-chargers, LiFePO4 batteries, MPPT controllers. Pricelist 2026-05-27.')
ON CONFLICT (id) DO NOTHING;

-- ── LiFePO4 Batteries ─────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('BAT-SRNE-001', 'Battery', 'LiFePO4 Wall Mount 2.56kWh/12V',
   '12.8V / 200Ah / 2.56kWh — EOS02B-12', 'pc', 1794000, 2153000, 'SUP-007',
   'Wall mount. 6,000 cycles at 80% DoD. Max parallel: 4. WiFi monitoring.',
   '{"ah": 200, "voltage": 12.8, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-SRNE-002', 'Battery', 'LiFePO4 Wall Mount 2.56kWh/24V',
   '25.6V / 100Ah / 2.56kWh — EOS02B-24', 'pc', 1932000, 2318000, 'SUP-007',
   'Wall mount. 6,000 cycles at 80% DoD. Max parallel: 4. WiFi monitoring.',
   '{"ah": 100, "voltage": 25.6, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 4}'::jsonb),

  ('BAT-SRNE-003', 'Battery', 'LiFePO4 Rack Mount 5.12kWh/48V',
   '51.2V / 100Ah / 5.12kWh — EOC05B-UL', 'pc', 3059000, 3671000, 'SUP-007',
   'Rack mount. 6,000 cycles at 80% DoD. Max parallel: 16. WiFi/BT monitoring.',
   '{"ah": 100, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 16}'::jsonb),

  ('BAT-SRNE-004', 'Battery', 'LiFePO4 Wall Mount 5.12kWh/48V (SE05B)',
   '51.2V / 100Ah / 5.12kWh — SE05B', 'pc', 3059000, 3671000, 'SUP-007',
   'Wall mount. 6,000 cycles at 80% DoD. Max parallel: 16. WiFi/BT monitoring.',
   '{"ah": 100, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 16}'::jsonb),

  ('BAT-SRNE-005', 'Battery', 'LiFePO4 Wall Mount 10.49kWh/48V (SE10B)',
   '51.2V / 205Ah / 10.49kWh — SE10B', 'pc', 5382000, 6458000, 'SUP-007',
   'Wall mount. 6,000 cycles at 80% DoD. Max parallel: 16. WiFi/BT monitoring.',
   '{"ah": 205, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 16}'::jsonb),

  ('BAT-SRNE-006', 'Battery', 'LiFePO4 Wall Mount 16.07kWh/48V (SE16B-Pro)',
   '51.2V / 314Ah / 16.07kWh — SE16B-Pro', 'pc', 7820000, 9384000, 'SUP-007',
   'Wall mount. 8,000 cycles at 80% DoD (highest cycle life). Built-in 240A breaker. Max parallel: 16.',
   '{"ah": 314, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 16}'::jsonb),

  ('BAT-SRNE-007', 'Battery', 'LiFePO4 Expansion Pack 5.12kWh/48V (EOV05B)',
   '51.2V / 100Ah / 5.12kWh — EOV05B', 'pc', 3082000, 3698000, 'SUP-007',
   'Stackable expansion pack for EOT05S all-in-one system. Max 4 banks in parallel.',
   '{"ah": 100, "voltage": 51.2, "dod_rated": 0.8, "chemistry": "LiFePO4", "is_complete_bank": true, "max_parallel": 4}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- ── Inverter-Chargers ─────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('INV-SRNE-001', 'Inverter', 'Solar Inverter 1.5kW/12V MPPT',
   '1.5kW / 12V — HF1215S60-108', 'pc', 667000, 800000, 'SUP-007',
   'Single phase. 60A max charge. MPPT 15-90Vdc. Max PV: 1,000W. 2yr warranty.',
   '{"battery_voltage": 12, "inverter_kw": 1.5, "controller_type": "MPPT", "max_charge_a": 60, "max_oc_v": 108, "mppt_min_v": 15, "mppt_max_v": 90, "mppt_trackers": 1, "max_pv_power_per_tracker": 1000}'::jsonb),

  ('INV-SRNE-002', 'Inverter', 'Solar Inverter 3kW/24V MPPT',
   '3kW / 24V — HF2430S60-108', 'pc', 863000, 1036000, 'SUP-007',
   'Single phase. 60A max charge. MPPT 30-90Vdc. Max PV: 1,600W. 2yr warranty.',
   '{"battery_voltage": 24, "inverter_kw": 3.0, "controller_type": "MPPT", "max_charge_a": 60, "max_oc_v": 108, "mppt_min_v": 30, "mppt_max_v": 90, "mppt_trackers": 1, "max_pv_power_per_tracker": 1600}'::jsonb),

  ('INV-SRNE-003', 'Inverter', 'Solar Inverter 3.3kW/24V MPPT HV',
   '3.3kW / 24V — HF2430S80-H', 'pc', 989000, 1187000, 'SUP-007',
   'Single phase. 80A max charge. MPPT 120-500Vdc. Max PV: 4,000W. 2yr warranty.',
   '{"battery_voltage": 24, "inverter_kw": 3.3, "controller_type": "MPPT", "max_charge_a": 80, "max_oc_v": 500, "mppt_min_v": 120, "mppt_max_v": 500, "mppt_trackers": 1, "max_pv_power_per_tracker": 4000}'::jsonb),

  ('INV-SRNE-004', 'Inverter', 'Solar Inverter 5kW/48V MPPT (Parallel)',
   '5kW / 48V — AFP4850S100-H', 'pc', 1380000, 1656000, 'SUP-007',
   'Single/3-phase parallel (up to 6 units). 100A max charge. MPPT 60-450Vdc. Max PV: 7,500W. 2yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 5.0, "controller_type": "MPPT", "max_charge_a": 100, "max_oc_v": 500, "mppt_min_v": 60, "mppt_max_v": 450, "mppt_trackers": 1, "max_pv_power_per_tracker": 7500}'::jsonb),

  ('INV-SRNE-005', 'Inverter', 'Solar Inverter 6kW/48V Dual MPPT (Parallel)',
   '6kW / 48V — AEP4860S135-H', 'pc', 1920000, 2304000, 'SUP-007',
   'Single/3-phase parallel. 2x MPPT, 135A charge. 6kW+6kW PV input. 5yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 6.0, "controller_type": "MPPT", "max_charge_a": 135, "max_oc_v": 500, "mppt_min_v": 65, "mppt_max_v": 450, "mppt_trackers": 2, "max_pv_power_per_tracker": 6000}'::jsonb),

  ('INV-SRNE-006', 'Inverter', 'Hybrid Inverter 6kW/48V WiFi (Parallel)',
   '6kW / 48V — HYP4860S100-H', 'pc', 1840000, 2208000, 'SUP-007',
   'Single/3-phase parallel. 2x MPPT, 100A charge. WiFi standard. 4,500W+4,500W PV. 2yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 6.0, "controller_type": "MPPT", "max_charge_a": 100, "max_oc_v": 550, "mppt_min_v": 120, "mppt_max_v": 480, "mppt_trackers": 2, "max_pv_power_per_tracker": 4500}'::jsonb),

  ('INV-SRNE-007', 'Inverter', 'Grid/Off-Grid Hybrid Inverter 6kW/48V (HESP)',
   '6kW / 48V — HESP4860S100-H', 'pc', 3059000, 3671000, 'SUP-007',
   'Grid + off-grid hybrid. 100A MPPT. Waterproof. Parallel up to 6. 5yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 6.0, "controller_type": "MPPT", "max_charge_a": 100, "max_oc_v": 500, "mppt_min_v": 60, "mppt_max_v": 450, "mppt_trackers": 1, "max_pv_power_per_tracker": 6000}'::jsonb),

  ('INV-SRNE-008', 'Inverter', 'Solar Inverter 10kW/48V Dual MPPT (Parallel)',
   '10kW / 48V — ASP48100S200-H', 'pc', 3450000, 4140000, 'SUP-007',
   'Single/3-phase parallel. 2x MPPT, 200A charge. 5,500W+5,500W PV. 2yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 10.0, "controller_type": "MPPT", "max_charge_a": 200, "max_oc_v": 500, "mppt_min_v": 125, "mppt_max_v": 425, "mppt_trackers": 2, "max_pv_power_per_tracker": 5500}'::jsonb),

  ('INV-SRNE-009', 'Inverter', 'Solar Inverter 12kW/48V Dual MPPT (Parallel)',
   '12kW / 48V — ASP48120S200-H', 'pc', 3680000, 4416000, 'SUP-007',
   'Single/3-phase parallel. 2x MPPT, 200A charge. 6,600W+6,600W PV. 2yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 12.0, "controller_type": "MPPT", "max_charge_a": 200, "max_oc_v": 500, "mppt_min_v": 125, "mppt_max_v": 425, "mppt_trackers": 2, "max_pv_power_per_tracker": 6600}'::jsonb),

  ('INV-SRNE-010', 'Inverter', 'Solar Inverter 20kW/48V 3-Phase',
   '20kW / 48V — ASP48200SH3', 'pc', 6670000, 8004000, 'SUP-007',
   '3-phase 230/400Vac. 360A charge/discharge. 2x MPPT 160-800Vdc. Max PV: 15kW+15kW. 2yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 20.0, "controller_type": "MPPT", "max_charge_a": 360, "max_oc_v": 1000, "mppt_min_v": 160, "mppt_max_v": 800, "mppt_trackers": 2, "max_pv_power_per_tracker": 15000}'::jsonb),

  ('INV-SRNE-011', 'Inverter', 'Hybrid Inverter 12kW/48V 3-Phase (HESP)',
   '12kW / 48V 3-phase — HESP48120H3', 'pc', 5600000, 6720000, 'SUP-007',
   'Grid+off-grid hybrid. 260A charge. 2x MPPT 200-650Vdc. 9kW+9kW PV. Waterproof IP65. 5yr warranty.',
   '{"battery_voltage": 48, "inverter_kw": 12.0, "controller_type": "MPPT", "max_charge_a": 260, "max_oc_v": 800, "mppt_min_v": 200, "mppt_max_v": 650, "mppt_trackers": 2, "max_pv_power_per_tracker": 9000}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- ── MPPT Charge Controllers ───────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('CHG-SRNE-001', 'Charge Controller', 'MPPT Charge Controller 20A/12-24V',
   '20A MPPT, 12V/24V — Shiner2420', 'pc', 133000, 160000, 'SUP-007',
   'Max PV voltage 60Vdc. Heat sink cooling. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 24, "max_charge_a": 20, "max_oc_v": 60}'::jsonb),

  ('CHG-SRNE-002', 'Charge Controller', 'MPPT Charge Controller 30A/12-24V',
   '30A MPPT, 12V/24V — Shiner2430', 'pc', 190000, 228000, 'SUP-007',
   'Max PV voltage 100Vdc. Heat sink cooling. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 24, "max_charge_a": 30, "max_oc_v": 100}'::jsonb),

  ('CHG-SRNE-003', 'Charge Controller', 'MPPT Charge Controller 60A/12-24V',
   '60A MPPT, 12V/24V — Shiner2460', 'pc', 350000, 420000, 'SUP-007',
   'Max PV voltage 100Vdc. Heat sink cooling. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 24, "max_charge_a": 60, "max_oc_v": 100}'::jsonb),

  ('CHG-SRNE-004', 'Charge Controller', 'MPPT Charge Controller 60A/12-48V Fan',
   '60A MPPT, 12-48V — MF4860N15', 'pc', 480000, 576000, 'SUP-007',
   'Max PV voltage 145Vdc. Fan cooling. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 48, "max_charge_a": 60, "max_oc_v": 145}'::jsonb),

  ('CHG-SRNE-005', 'Charge Controller', 'MPPT Charge Controller 100A/12-48V HV',
   '100A MPPT, 12-48V — MC48100N25', 'pc', 1050000, 1260000, 'SUP-007',
   'Max PV voltage 250Vdc. Heat sink cooling. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 48, "max_charge_a": 100, "max_oc_v": 250}'::jsonb),

  ('CHG-SRNE-006', 'Charge Controller', 'MPPT Charge Controller 100A/12-48V 500V Fan',
   '100A MPPT, 12-48V — MF48100N50', 'pc', 1380000, 1656000, 'SUP-007',
   'Max PV voltage 500Vdc. Fan cooling. High voltage string compatible. 3yr warranty.',
   '{"controller_type": "MPPT", "battery_voltage": 48, "max_charge_a": 100, "max_oc_v": 500}'::jsonb)

ON CONFLICT (id) DO NOTHING;

-- ── Solar Panel ───────────────────────────────────────────────────────────────
INSERT INTO catalog_items (id, category, name, spec, uom, buy_price, sell_price, supplier_id, notes, spec_data)
VALUES
  ('SOL-SRNE-001', 'Solar Panel', 'Monocrystalline Panel 600Wp',
   '600W, Mono, 2278x1134x30mm — GS600N-144M', 'pc', 320250, 384300, 'SUP-007',
   '182x91mm half-cut cells, 6x24 layout. Anti-reflection glass. MC4 cable. 31.5kg. 1yr warranty.',
   '{"wp": 600}'::jsonb)

ON CONFLICT (id) DO NOTHING;
