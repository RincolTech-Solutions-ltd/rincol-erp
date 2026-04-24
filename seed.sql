-- Rincol Web ERP — Seed Data (run AFTER schema.sql)
-- Paste into Supabase SQL Editor

-- ── Settings ──────────────────────────────────────────────────────────────────
INSERT INTO settings VALUES ('qt_year', '2025') ON CONFLICT DO NOTHING;
INSERT INTO settings VALUES ('qt_counter', '0') ON CONFLICT DO NOTHING;

-- ── Suppliers / Service Providers ─────────────────────────────────────────────
INSERT INTO service_providers (id,name,contact_person,phone,email,location,categories,notes) VALUES
  ('SUP-001','Growatt International','','','','China / Kampala distributor','Inverter','Hybrid inverters 3.5kW-5kW'),
  ('SUP-002','Local Battery Supplier (Kampala)','','','','Kampala','Battery','Deep cycle sealed and tubular gel'),
  ('SUP-003','Local Inverter Supplier (Kampala)','','','','Kampala','Inverter, Charge Controller','700VA-3500VA inverter chargers, MPPT'),
  ('SUP-004','Hardware / Electrical Supplier','','','','Kampala','Cable, Accessory','Cables, accessories, switchgear'),
  ('SUP-005','Lithium Battery Supplier','','','','Kampala','Battery','LiFePO4 and Bodawerk smart batteries'),
  ('SUP-006','AE-Solar / Solar Panel Supplier','','','','Kampala','Solar Panel','AE-Solar USA monocrystalline modules')
ON CONFLICT (id) DO NOTHING;

-- ── Catalog Items ─────────────────────────────────────────────────────────────
INSERT INTO catalog_items (id,category,name,spec,uom,buy_price,sell_price,supplier_id,notes) VALUES
  -- Batteries
  ('BAT-001','Battery','Deep Cycle Sealed Battery 100Ah/12V','100Ah, 12V, C10, Sealed VRLA','pc',480000,620000,'SUP-002',''),
  ('BAT-002','Battery','Deep Cycle Sealed Battery 200Ah/12V','200Ah, 12V, C10, Sealed VRLA','pc',1050000,1350000,'SUP-002',''),
  ('BAT-003','Battery','Deep Cycle Tubular Gel Battery 150Ah/12V','150Ah, 12V, Tubular Gel','pc',850000,1100000,'SUP-002',''),
  ('BAT-004','Battery','Deep Cycle Tubular Gel Battery 200Ah/12V','200Ah, 12V, Tubular Gel','pc',1100000,1400000,'SUP-002',''),
  ('BAT-005','Battery','Deep Cycle Sealed Battery 400Ah/2V (set of 6)','400Ah, 2V cells, set of 6 (48V bank)','set',2500000,3200000,'SUP-002','6 cells in series = 48V'),
  ('BAT-006','Battery','Lithium Ion (LiFePO4) Battery 100Ah/12.8V','100Ah, 12.8V, LiFePO4 wallmount','pc',750000,1000000,'SUP-005',''),
  ('BAT-007','Battery','Lithium Ion (LiFePO4) Battery 200Ah/12.8V','200Ah, 12.8V, LiFePO4','pc',1000000,1300000,'SUP-005',''),
  ('BAT-008','Battery','Bodawerk Smart Battery 4.6kWh 48V','4.6kWh, 48V, Smart BMS, LiFePO4','pc',4500000,6000000,'SUP-005',''),
  ('BAT-009','Battery','Battery Cage/Rack','Steel protective enclosure for batteries','pc',70000,120000,'SUP-004',''),
  ('BAT-010','Battery','Battery Lugged Cables','Interconnection cables, lugged ends','pair',15000,30000,'SUP-004',''),
  -- Inverters
  ('INV-001','Inverter','Inverter Charger 700VA 12VDC/240VAC','700VA, 12V DC, 240V AC, Pure Sine','pc',300000,420000,'SUP-003','Entry level'),
  ('INV-002','Inverter','Inverter Charger 700VA 24VDC/240VAC','700VA, 24V DC, 240V AC, Pure Sine','pc',305000,430000,'SUP-003',''),
  ('INV-003','Inverter','Inverter Charger 1100VA 12VDC/240VAC','1100VA, 12V, DSP Pure Sine Wave','pc',450000,600000,'SUP-003',''),
  ('INV-004','Inverter','Inverter Charger 1600VA 24VDC/240VAC DSP','1600VA, 24V, DSP Sine Wave Hybrid','pc',750000,950000,'SUP-003',''),
  ('INV-005','Inverter','Inverter Charger 2500VA 24VDC/240VAC','2500VA, 24V, Pure Sine Wave','pc',900000,1100000,'SUP-003',''),
  ('INV-006','Inverter','Inverter Charger 3500VA 24VDC/240VAC DSP','3500VA, 24V, DSP Sine Wave','pc',1200000,1500000,'SUP-003',''),
  ('INV-007','Inverter','Hybrid Inverter 3.5kW 48VDC/240VAC MPPT','3.5kW, 48V, Hybrid with MPPT','pc',2000000,2800000,'SUP-001',''),
  ('INV-008','Inverter','Growatt Hybrid Inverter 3.5kW 48V','3.5kW, 48V, Growatt, Integrated MPPT','pc',2000000,2600000,'SUP-001',''),
  ('INV-009','Inverter','Growatt Hybrid Inverter 5kW 48V','5kW, 48V, Growatt, Integrated MPPT','pc',2800000,3800000,'SUP-001',''),
  ('INV-010','Inverter','Hybrid Inverter 5kW 48VDC/240VAC MPPT','5kW, 48V, Hybrid with MPPT','pc',3300000,4500000,'SUP-001',''),
  -- Solar Panels
  ('SOL-001','Solar Panel','Solar Module Monocrystalline 160Wp AE-Solar','160W, Monocrystalline, AE-Solar USA','pc',280000,380000,'SUP-006',''),
  ('SOL-002','Solar Panel','Solar Module Monocrystalline 495Wp AE-Solar','495W, Monocrystalline, AE-Solar USA','pc',320000,450000,'SUP-006',''),
  ('SOL-003','Solar Panel','Solar Module Monocrystalline 550Wp AE-Solar','550W, Monocrystalline, AE-Solar USA','pc',350000,480000,'SUP-006','Most common'),
  ('SOL-004','Solar Panel','Solar Module Monocrystalline 620Wp AE-Solar','620W, Monocrystalline, AE-Solar USA','pc',400000,550000,'SUP-006','Premium'),
  ('SOL-005','Solar Panel','Mounting Rack for Solar Modules (theft-proof)','Galvanised steel, anti-theft bolts','pc',60000,100000,'SUP-004','Per panel'),
  ('SOL-006','Solar Panel','Panel Frame / Support Structure','Aluminium/Steel frame','pc',30000,55000,'SUP-004',''),
  -- Charge Controllers
  ('CHG-001','Charge Controller','MPPT Charge Controller 30A','30A MPPT, 12/24V','pc',180000,250000,'SUP-003',''),
  ('CHG-002','Charge Controller','MPPT Charge Controller 40A','40A MPPT, 12/24/48V','pc',280000,400000,'SUP-003',''),
  -- Cables
  ('CAB-001','Cable','Red Single Core Cable 2.5sqmm','2.5mm2, single core, red','m',4500,7000,'SUP-004',''),
  ('CAB-002','Cable','Black Single Core Cable 2.5sqmm','2.5mm2, single core, black','m',4500,7000,'SUP-004',''),
  ('CAB-003','Cable','3 Core Cable 2.5sqmm','2.5mm2, 3-core, PVC insulated','m',7000,10000,'SUP-004','AC load'),
  ('CAB-004','Cable','4 Core Cable 2.5sqmm','2.5mm2, 4-core, PVC insulated','m',9000,13000,'SUP-004','AC with earth'),
  ('CAB-005','Cable','UV Cable 4mm (outdoor rated)','4mm2, UV resistant, outdoor','m',8000,12000,'SUP-004','PV cable'),
  ('CAB-006','Cable','UV Cable 6mm (outdoor rated)','6mm2, UV resistant, outdoor','m',12000,18000,'SUP-004','PV cable'),
  ('CAB-007','Cable','UV Cable 10mm (outdoor rated)','10mm2, UV resistant, outdoor','m',18000,25000,'SUP-004','Long PV runs'),
  ('CAB-008','Cable','16sqmm Power Cable','16mm2, heavy duty power cable','m',22000,32000,'SUP-004','High current'),
  ('CAB-009','Cable','1.5sqmm Twin Wire','1.5mm2, twin flat wire','m',2500,4000,'SUP-004','Lighting'),
  ('CAB-010','Cable','Cable Conduit 25mm','25mm PVC conduit','m',3000,5000,'SUP-004',''),
  ('CAB-011','Cable','Trunking','PVC cable management trunking','m',8000,15000,'SUP-004',''),
  ('CAB-012','Cable','Cable Ties (pack of 100)','Nylon cable ties, mixed sizes','pack',5000,10000,'SUP-004',''),
  -- Accessories
  ('ACC-001','Accessory','DC Circuit Breaker 20A','20A, DC rated','pc',25000,40000,'SUP-004',''),
  ('ACC-002','Accessory','DC Circuit Breaker 30A','30A, DC rated','pc',30000,45000,'SUP-004',''),
  ('ACC-003','Accessory','Changeover Switch 16A','16A, manual changeover','pc',45000,70000,'SUP-004',''),
  ('ACC-004','Accessory','Changeover Switch 32A','32A, manual changeover','pc',60000,90000,'SUP-004','Heavy load'),
  ('ACC-005','Accessory','Wiring Accessories Bundle','Screws, connectors, tape, clips','lot',25000,40000,'SUP-004','Per job'),
  ('ACC-006','Accessory','PV Combiner Box 1-way','1-way MC4 combiner box','pc',80000,130000,'SUP-004',''),
  ('ACC-007','Accessory','Distribution Board 2-way','2-way MCB distribution board','pc',50000,80000,'SUP-004',''),
  ('ACC-008','Accessory','Surge Arrestor','AC surge protection device','pc',35000,55000,'SUP-004',''),
  ('ACC-009','Accessory','Earthing System / Earthing Works','Earth rod, clamps, conductor','lot',80000,150000,'SUP-004',''),
  ('ACC-010','Accessory','Wall Socket (single)','Single 13A wall socket','pc',12000,20000,'SUP-004',''),
  ('ACC-011','Accessory','Light Switch 1-gang','1-gang light switch','pc',8000,15000,'SUP-004',''),
  ('ACC-012','Accessory','Light Switch 2-gang','2-gang light switch','pc',10000,18000,'SUP-004',''),
  ('ACC-013','Accessory','20W LED Flood Light','20W, LED, outdoor','pc',50000,80000,'SUP-004',''),
  ('ACC-014','Accessory','Motion Sensor Light','PIR motion sensor ceiling light','pc',35000,60000,'SUP-004',''),
  -- Services
  ('SVC-001','Service','Labour / Transportation (small job)','Installation within Kampala, 1 day','job',0,150000,'',''),
  ('SVC-002','Service','Labour / Transportation (standard job)','Installation within Kampala, 1-2 days','job',0,250000,'','Most common'),
  ('SVC-003','Service','Labour / Transportation (medium job)','Installation Kampala suburbs, 2 days','job',0,350000,'',''),
  ('SVC-004','Service','Labour / Transportation (large/upcountry job)','Installation upcountry or complex, 3+ days','job',0,600000,'',''),
  ('SVC-005','Service','System Design / Sizing Consultation','Load analysis, system sizing report','job',0,100000,'','')
ON CONFLICT (id) DO NOTHING;

-- ── System Templates ──────────────────────────────────────────────────────────
INSERT INTO system_templates (id,name,description,sort_order) VALUES
  ('TPL-001','Small System — 700VA 12V','Inverter + 100Ah battery. Lights, phone charging, small TV.',1),
  ('TPL-002','Medium System — 1100VA 12V','Inverter + 200Ah battery. Standard home backup.',2),
  ('TPL-003','Standard System — 1600VA 24V','DSP hybrid + 2x 200Ah batteries. Fridge-capable.',3),
  ('TPL-004','Comfort System — 2500VA 24V','Inverter + 2x tubular gel 200Ah. Larger home.',4),
  ('TPL-005','Large System — 3.5kW 48V Hybrid','Growatt hybrid + 4x 200Ah. Heavy load / office.',5),
  ('TPL-006','Small System + 1 Solar Panel — 700VA','700VA + 100Ah + 1x 495Wp panel. Off-grid small.',6),
  ('TPL-007','Standard System + 2 Solar Panels — 1600VA','1600VA + 2x 200Ah + 2x 550Wp. Solar-assisted.',7)
ON CONFLICT (id) DO NOTHING;

-- ── Template Items ────────────────────────────────────────────────────────────
INSERT INTO template_items (template_id,catalog_item_id,description,uom,qty) VALUES
  -- TPL-001: 700VA 12V
  ('TPL-001','INV-001','Inverter Charger 700VA 12VDC/240VAC — 700VA, 12V DC, 240V AC, Pure Sine','pc',1),
  ('TPL-001','BAT-001','Deep Cycle Sealed Battery 100Ah/12V — 100Ah, 12V, C10, Sealed VRLA','pc',1),
  ('TPL-001','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-001','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',1),
  ('TPL-001','CAB-001','Red Single Core Cable 2.5sqmm','m',10),
  ('TPL-001','CAB-002','Black Single Core Cable 2.5sqmm','m',10),
  ('TPL-001','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-001','SVC-002','Labour / Transportation (standard job)','job',1),
  -- TPL-002: 1100VA 12V
  ('TPL-002','INV-003','Inverter Charger 1100VA 12VDC/240VAC — 1100VA, 12V, DSP Pure Sine Wave','pc',1),
  ('TPL-002','BAT-002','Deep Cycle Sealed Battery 200Ah/12V — 200Ah, 12V, C10, Sealed VRLA','pc',1),
  ('TPL-002','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-002','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',1),
  ('TPL-002','CAB-001','Red Single Core Cable 2.5sqmm','m',15),
  ('TPL-002','CAB-002','Black Single Core Cable 2.5sqmm','m',15),
  ('TPL-002','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-002','SVC-002','Labour / Transportation (standard job)','job',1),
  -- TPL-003: 1600VA 24V
  ('TPL-003','INV-004','Inverter Charger 1600VA 24VDC/240VAC DSP — 1600VA, 24V, DSP Sine Wave Hybrid','pc',1),
  ('TPL-003','BAT-002','Deep Cycle Sealed Battery 200Ah/12V — 200Ah, 12V, C10, Sealed VRLA','pc',2),
  ('TPL-003','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-003','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',2),
  ('TPL-003','CAB-001','Red Single Core Cable 2.5sqmm','m',15),
  ('TPL-003','CAB-002','Black Single Core Cable 2.5sqmm','m',15),
  ('TPL-003','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-003','SVC-003','Labour / Transportation (medium job)','job',1),
  -- TPL-004: 2500VA 24V
  ('TPL-004','INV-005','Inverter Charger 2500VA 24VDC/240VAC — 2500VA, 24V, Pure Sine Wave','pc',1),
  ('TPL-004','BAT-004','Deep Cycle Tubular Gel Battery 200Ah/12V — 200Ah, 12V, Tubular Gel','pc',2),
  ('TPL-004','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-004','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',2),
  ('TPL-004','CAB-001','Red Single Core Cable 2.5sqmm','m',20),
  ('TPL-004','CAB-002','Black Single Core Cable 2.5sqmm','m',20),
  ('TPL-004','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-004','SVC-003','Labour / Transportation (medium job)','job',1),
  -- TPL-005: 3.5kW 48V
  ('TPL-005','INV-008','Growatt Hybrid Inverter 3.5kW 48V — 3.5kW, 48V, Growatt, Integrated MPPT','pc',1),
  ('TPL-005','BAT-002','Deep Cycle Sealed Battery 200Ah/12V — 200Ah, 12V, C10, Sealed VRLA','pc',4),
  ('TPL-005','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',2),
  ('TPL-005','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',4),
  ('TPL-005','CAB-001','Red Single Core Cable 2.5sqmm','m',20),
  ('TPL-005','CAB-002','Black Single Core Cable 2.5sqmm','m',20),
  ('TPL-005','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-005','SVC-004','Labour / Transportation (large/upcountry job)','job',1),
  -- TPL-006: 700VA + 1 solar
  ('TPL-006','INV-001','Inverter Charger 700VA 12VDC/240VAC — 700VA, 12V DC, 240V AC, Pure Sine','pc',1),
  ('TPL-006','BAT-001','Deep Cycle Sealed Battery 100Ah/12V — 100Ah, 12V, C10, Sealed VRLA','pc',1),
  ('TPL-006','SOL-002','Solar Module Monocrystalline 495Wp AE-Solar — 495W, Monocrystalline','pc',1),
  ('TPL-006','SOL-005','Mounting Rack for Solar Modules (theft-proof) — Galvanised steel','pc',1),
  ('TPL-006','CAB-005','UV Cable 4mm (outdoor rated) — 4mm2, UV resistant','m',10),
  ('TPL-006','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-006','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',1),
  ('TPL-006','CAB-001','Red Single Core Cable 2.5sqmm','m',10),
  ('TPL-006','CAB-002','Black Single Core Cable 2.5sqmm','m',10),
  ('TPL-006','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-006','SVC-002','Labour / Transportation (standard job)','job',1),
  -- TPL-007: 1600VA + 2 solar
  ('TPL-007','INV-004','Inverter Charger 1600VA 24VDC/240VAC DSP — 1600VA, 24V, DSP Sine Wave Hybrid','pc',1),
  ('TPL-007','BAT-002','Deep Cycle Sealed Battery 200Ah/12V — 200Ah, 12V, C10, Sealed VRLA','pc',2),
  ('TPL-007','SOL-003','Solar Module Monocrystalline 550Wp AE-Solar — 550W, Monocrystalline','pc',2),
  ('TPL-007','SOL-005','Mounting Rack for Solar Modules (theft-proof) — Galvanised steel','pc',2),
  ('TPL-007','CAB-006','UV Cable 6mm (outdoor rated) — 6mm2, UV resistant','m',15),
  ('TPL-007','BAT-009','Battery Cage/Rack — Steel protective enclosure','pc',1),
  ('TPL-007','BAT-010','Battery Lugged Cables — Interconnection cables, lugged ends','pair',2),
  ('TPL-007','CAB-001','Red Single Core Cable 2.5sqmm','m',15),
  ('TPL-007','CAB-002','Black Single Core Cable 2.5sqmm','m',15),
  ('TPL-007','ACC-005','Wiring Accessories Bundle — Screws, connectors, tape, clips','lot',1),
  ('TPL-007','SVC-003','Labour / Transportation (medium job)','job',1);
