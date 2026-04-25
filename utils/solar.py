"""Solar sizing calculation engine — Rincol Tech Solutions.

All formulas verified against three real Rincol projects:
  Duncan Atulinda (Kigo, 12V Li-ion, April 2026)
  Mutegs (Kigo, 48V Lead Acid, May 2024)
  Lynda Michelle Medical Centre (Kigo, 48V Lead Acid, Dec 2022)

Appliance load_type values:
  'standard' — power_w × power_factor × quantity × hours_per_day
  'fridge'   — annual_kwh / 365 for daily energy; peak_w used for inverter sizing only
"""
import math

# Uganda standard defaults
DEFAULT_PEAK_SUN_HOURS    = 5.5
DEFAULT_PERFORMANCE_RATIO = 0.75
DEFAULT_DOD               = 0.80
DEFAULT_INVERTER_EFF      = 0.90
DEFAULT_CABLE_EFF         = 0.95
DEFAULT_DAYS_AUTONOMY     = 1
DEFAULT_INVERTER_IDLE_W   = 50    # inverter no-load draw; added to daily load before battery sizing

# 48V MPPT lower-bound input voltage (panels in series must exceed this)
MIN_INVERTER_INPUT_V = 120


def calc_sizing(params, appliances):
    """Run full 6-step solar sizing calculation.

    Args:
        params: dict — keys match solar_sizings table columns
        appliances: list of dicts — each has:
            name, load_type ('standard'|'fridge'),
            power_w, power_factor, quantity, hours_per_day,
            annual_kwh (for fridges), peak_w (for fridges, inverter sizing),
            included (bool)

    Returns:
        dict of all calculated scalars + annotated appliances list
    """
    # ── Step 1: Daily energy load ─────────────────────────────────────────────
    total_daily_wh = 0.0
    peak_load_w    = 0.0
    for a in appliances:
        if not a.get('included', True):
            a['daily_wh'] = 0.0
            continue

        load_type = a.get('load_type', 'standard')

        if load_type == 'fridge':
            # Fridge: annual kWh label ÷ 365 = daily Wh
            annual_kwh = float(a.get('annual_kwh', 0))
            qty        = int(a.get('quantity', 1))
            wh         = annual_kwh * 1000 / 365 * qty
            # Peak demand: use peak_w (compressor startup), or fall back to power_w
            pw_peak = float(a.get('peak_w', 0) or a.get('power_w', 0))
            peak_load_w += pw_peak * qty
        else:
            # Standard: power_w × power_factor × qty × hours
            pw  = float(a['power_w'])
            pf  = float(a.get('power_factor', 1.0))
            qty = int(a.get('quantity', 1))
            hrs = float(a.get('hours_per_day', 0))
            wh  = pw * pf * qty * hrs
            peak_load_w += pw * qty

        a['daily_wh'] = round(wh, 2)
        total_daily_wh += wh

    # Add inverter idle draw: inverter runs 24 hrs/day overnight even with no load
    inverter_idle_w    = float(params.get('inverter_idle_w', DEFAULT_INVERTER_IDLE_W))
    inverter_idle_wh   = inverter_idle_w * 24
    total_daily_wh    += inverter_idle_wh

    # ── Step 2: Battery sizing ────────────────────────────────────────────────
    system_v   = int(params.get('system_voltage', 48))
    dod        = float(params.get('dod', DEFAULT_DOD))
    inv_eff    = float(params.get('inverter_efficiency', DEFAULT_INVERTER_EFF))
    cable_eff  = float(params.get('cable_efficiency', DEFAULT_CABLE_EFF))
    days       = int(params.get('days_autonomy', DEFAULT_DAYS_AUTONOMY))
    battery_v  = float(params.get('battery_voltage', 12))
    battery_ah = float(params.get('battery_ah', 200))
    battery_type     = params.get('battery_type', 'Li-ion')
    battery_is_bank  = bool(params.get('battery_is_bank', False))

    # LiFePO4 / Li-ion must NEVER be put in series — they are complete voltage packs.
    # Also honour the explicit battery_is_bank flag (for 24V / 48V assembled banks).
    is_lithium = any(x in battery_type.lower() for x in ('li-ion', 'lifepo4', 'lfp', 'lithium'))
    no_series  = battery_is_bank or is_lithium

    denominator = system_v * dod * inv_eff * cable_eff
    battery_ah_min = (total_daily_wh * days / denominator) if denominator > 0 else 0

    if no_series:
        batteries_in_series = 1
    else:
        batteries_in_series = max(1, round(system_v / battery_v))

    batteries_in_parallel = max(1, math.ceil(battery_ah_min / battery_ah)) if battery_ah > 0 else 1
    total_batteries = batteries_in_series * batteries_in_parallel

    # ── Step 3: Solar panel sizing ────────────────────────────────────────────
    psh       = float(params.get('peak_sun_hours', DEFAULT_PEAK_SUN_HOURS))
    pr        = float(params.get('performance_ratio', DEFAULT_PERFORMANCE_RATIO))
    panel_wp  = float(params.get('panel_wp', 550))
    panel_voc = float(params.get('panel_voc', 40.0))
    panel_isc = float(params.get('panel_isc', 0.0))

    mppt_trackers                 = int(params.get('mppt_trackers', 1))
    mppt_min_v                    = float(params.get('mppt_min_v', 0))
    mppt_max_v                    = float(params.get('mppt_max_v', 0))
    max_oc_v                      = float(params.get('max_oc_v', 0))
    max_input_current_per_tracker = float(params.get('max_input_current_per_tracker', 0))
    max_isc_per_tracker           = float(params.get('max_isc_per_tracker', 0))
    max_pv_power_per_tracker      = float(params.get('max_pv_power_per_tracker', 0))

    required_wp      = (total_daily_wh / (psh * pr)) if (psh * pr) > 0 else 0
    panels_by_energy = max(1, math.ceil(required_wp / panel_wp)) if panel_wp > 0 else 1

    panel_array_flags = []

    # --- Determine panels in series from MPPT voltage range ---
    # Vmpp ≈ Voc × 0.82 (typical mono). Used for MPPT window check.
    panel_vmpp = panel_voc * 0.82 if panel_voc > 0 else 0

    if system_v >= 48 and mppt_min_v > 0 and mppt_max_v > 0 and panel_vmpp > 0:
        # Use real MPPT range from inverter spec
        min_series_v = math.ceil(mppt_min_v / panel_vmpp)
        max_series_v = math.floor(mppt_max_v / panel_vmpp)
        panels_in_series = max(1, min_series_v)
        if panels_in_series > max_series_v:
            panel_array_flags.append(
                f"No valid series count: MPPT min needs {min_series_v}S but MPPT max allows only {max_series_v}S. Check panel Voc/inverter MPPT range.")
    elif system_v >= 48 and panel_voc > 0:
        # Fall back to hardcoded 120 V floor
        panels_in_series = math.ceil(MIN_INVERTER_INPUT_V / (panel_voc * 0.8))
    else:
        panels_in_series = 1  # 12V / PWM systems

    # --- Hard OC voltage safety check ---
    if max_oc_v > 0 and panel_voc > 0:
        max_series_oc = math.floor(max_oc_v / panel_voc)
        if panels_in_series > max_series_oc:
            panel_array_flags.append(
                f"DANGER: {panels_in_series}S × {panel_voc}V Voc = {panels_in_series * panel_voc:.0f}V "
                f"exceeds max OC {max_oc_v:.0f}V. Capped at {max_series_oc}S.")
            panels_in_series = max(1, max_series_oc)

    # --- Strings from energy requirement ---
    strings_by_energy = max(1, math.ceil(panels_by_energy / panels_in_series)) if panels_in_series > 0 else 1

    # --- Tracker current limit: max strings per tracker ---
    if max_input_current_per_tracker > 0 and panel_isc > 0:
        max_strings_per_tracker = max(1, math.floor(max_input_current_per_tracker / panel_isc))
    else:
        max_strings_per_tracker = 999  # unknown — no limit applied

    max_total_strings = max_strings_per_tracker * mppt_trackers

    strings_total = strings_by_energy
    if max_total_strings < 999 and strings_total > max_total_strings:
        panel_array_flags.append(
            f"Array needs {strings_total} strings but inverter supports max {max_total_strings} "
            f"({mppt_trackers} tracker(s) × {max_strings_per_tracker} strings each at {max_input_current_per_tracker}A/tracker). "
            f"Consider larger inverter or reducing load.")
        strings_total = max_total_strings

    strings_per_tracker = math.ceil(strings_total / mppt_trackers)
    panels_recommended  = panels_in_series * strings_total

    # --- Isc safety check ---
    if max_isc_per_tracker > 0 and panel_isc > 0:
        isc_actual = panel_isc * strings_per_tracker
        if isc_actual > max_isc_per_tracker:
            panel_array_flags.append(
                f"WARNING: Isc per tracker {isc_actual:.1f}A ({strings_per_tracker} strings × {panel_isc}A) "
                f"exceeds max {max_isc_per_tracker}A. Reduce strings per tracker.")

    # --- Power per tracker check ---
    if max_pv_power_per_tracker > 0 and panel_wp > 0:
        power_per_tracker = panel_wp * panels_in_series * strings_per_tracker
        total_max_power   = max_pv_power_per_tracker * mppt_trackers
        if power_per_tracker > max_pv_power_per_tracker:
            panel_array_flags.append(
                f"WARNING: {power_per_tracker:.0f}W per tracker exceeds inverter max {max_pv_power_per_tracker:.0f}W/tracker "
                f"(total capacity {total_max_power:.0f}W across {mppt_trackers} tracker(s)).")

    # --- Voltage override flag (for display) ---
    # True when series constraint forced more panels than energy alone required
    panels_by_voltage = panels_in_series  # kept for backward-compat with view template
    voltage_override  = panels_recommended > panels_by_energy

    # ── Step 4: Annual energy yield ───────────────────────────────────────────
    annual_yield_kwh = panel_wp * panels_recommended * psh * 365 * pr / 1000

    # ── Step 5: Financial appraisal ───────────────────────────────────────────
    panel_cost        = float(params.get('panel_cost', 0))
    battery_cost_each = float(params.get('battery_cost_each', 0))
    inverter_cost     = float(params.get('inverter_cost', 0))
    labour_transport  = float(params.get('labour_transport', 0))
    # battery_type already set in Step 2

    battery_cost_total = battery_cost_each * total_batteries
    panel_cost_total   = panel_cost * panels_recommended
    system_cost = panel_cost_total + battery_cost_total + inverter_cost + labour_transport

    # Lead acid needs replacement once in 10 years (Eastman tubular gel: ~5-7yr cycle life)
    maintenance_cost_10yr = battery_cost_total if battery_type == 'Lead Acid' else 0.0

    cost_of_ownership_10yr = system_cost + maintenance_cost_10yr
    ten_yr_yield = annual_yield_kwh * 10
    solar_cost_per_kwh = (cost_of_ownership_10yr / ten_yr_yield) if ten_yr_yield > 0 else 0

    utility_tariff    = float(params.get('utility_tariff', 897))
    tariff_escalation = float(params.get('tariff_escalation', 0.0))  # annual % / 100

    # 10-year savings: if escalation provided, compound year by year
    if tariff_escalation > 0:
        ten_yr_grid_cost = sum(
            annual_yield_kwh * utility_tariff * ((1 + tariff_escalation) ** yr)
            for yr in range(10)
        )
    else:
        ten_yr_grid_cost = ten_yr_yield * utility_tariff

    yaka_savings_10yr = ten_yr_grid_cost - cost_of_ownership_10yr

    # ── Step 6: Payback period ────────────────────────────────────────────────
    # Use same utility_tariff as Section C — payback = system_cost / (yield × tariff)
    annual_savings = annual_yield_kwh * utility_tariff
    payback_years  = (system_cost / annual_savings) if annual_savings > 0 else 0

    # ── Inverter sizing flag ──────────────────────────────────────────────────
    inverter_kw = float(params.get('inverter_kw', 3.5))
    peak_kw     = peak_load_w / 1000
    if peak_kw > inverter_kw:
        inverter_flag = f"UNDERSIZED — peak load {peak_kw:.1f} kW exceeds inverter {inverter_kw} kW. Upgrade required."
    elif peak_kw > inverter_kw * 0.85:
        inverter_flag = f"WARNING — peak load {peak_kw:.1f} kW is >85% of inverter capacity. Consider next tier up."
    else:
        inverter_flag = ''

    return {
        'total_daily_wh':        round(total_daily_wh, 2),
        'inverter_idle_wh':      round(inverter_idle_wh, 2),
        'peak_load_w':           round(peak_load_w, 2),
        'battery_ah_min':        round(battery_ah_min, 2),
        'batteries_in_series':   batteries_in_series,
        'batteries_in_parallel': batteries_in_parallel,
        'total_batteries':       total_batteries,
        'required_wp':           round(required_wp, 2),
        'panels_by_energy':      panels_by_energy,
        'panels_by_voltage':     panels_by_voltage,
        'panels_in_series':      panels_in_series,
        'strings_total':         strings_total,
        'strings_per_tracker':   strings_per_tracker,
        'voltage_override':      voltage_override,
        'panels_recommended':    panels_recommended,
        'annual_yield_kwh':      round(annual_yield_kwh, 2),
        'system_cost':           round(system_cost, 0),
        'maintenance_cost_10yr': round(maintenance_cost_10yr, 0),
        'solar_cost_per_kwh':    round(solar_cost_per_kwh, 2),
        'yaka_savings_10yr':     round(yaka_savings_10yr, 0),
        'payback_years':         round(payback_years, 2),
        'inverter_flag':         inverter_flag,
        'panel_array_flag':      ' | '.join(panel_array_flags),
        'appliances':            appliances,
    }


def build_bom(params, results):
    """Generate standard BoM line items from sizing results.

    Returns list of dicts: {description, uom, qty, unit_price, total}
    Items are in the standard Rincol BoM order.
    """
    items = []

    def add(desc, uom, qty, unit_price):
        items.append({
            'description': desc,
            'uom': uom,
            'qty': float(qty),
            'unit_price': round(float(unit_price), 0),
            'total': round(float(qty) * float(unit_price), 0),
        })

    sys_v        = int(params.get('system_voltage', 48))
    panel_wp     = float(params.get('panel_wp', 550))
    panel_isc    = float(params.get('panel_isc', 0))
    panel_cost   = float(params.get('panel_cost', 0))
    n_panels     = results['panels_recommended']
    strings_per_tracker = results.get('strings_per_tracker', 1)
    mppt_trackers       = int(params.get('mppt_trackers', 1))

    battery_ah   = float(params.get('battery_ah', 200))
    battery_v    = float(params.get('battery_voltage', 12))
    battery_type = params.get('battery_type', 'Li-ion')
    battery_cost = float(params.get('battery_cost_each', 0))
    n_batteries  = results['total_batteries']

    inverter_kw   = float(params.get('inverter_kw', 3.5))
    inverter_cost = float(params.get('inverter_cost', 0))

    labour_transport = float(params.get('labour_transport', 0))
    n_bat_strings    = results['batteries_in_parallel']

    # 1. Solar panels
    if panel_cost > 0:
        add(f"Solar Panel {panel_wp:.0f}Wp Monocrystalline", "pc", n_panels, panel_cost)

    # 2. Panel mounting frames
    add("Solar Panel Mounting Frame", "pc", n_panels, 90000)

    # 3. DC circuit breaker — sized from Isc × strings per tracker (NEC 690.9: 1.25× Isc)
    #    One CB per MPPT tracker input. Round up to standard sizes.
    _std_cb = [10, 16, 20, 25, 32, 40, 50, 63, 80, 100]
    if panel_isc > 0 and strings_per_tracker > 0:
        cb_a_raw = 1.25 * panel_isc * strings_per_tracker
        cb_a = next((s for s in _std_cb if s >= cb_a_raw), _std_cb[-1])
    else:
        cb_a = 30 if sys_v == 48 else 10
    add(f"DC Circuit Breaker {cb_a}A", "pc", mppt_trackers, 35000)

    # 4. Distribution board
    add("Two-way Distribution Board", "pc", 1, 45000)

    # 5. UV solar cable (60m for 48V, 30m for 12V)
    cable_m = 60 if sys_v == 48 else 30
    add("UV Solar Cable 6mm²", "m", cable_m, 6000)

    # 6. Lugged battery cables (3 per string for 48V, 2 for 12V)
    n_bat_cables = max(2, 3 * n_bat_strings) if sys_v == 48 else 2
    add("Lugged Battery Cable", "pc", n_bat_cables, 15000)

    # 7. Batteries
    if battery_cost > 0:
        batt_label = f"{battery_ah:.0f}Ah/{battery_v:.0f}V {battery_type}"
        add(f"Battery {batt_label}", "pc", n_batteries, battery_cost)

    # 8. Inverter
    if inverter_cost > 0:
        add(f"Hybrid Inverter {inverter_kw}kW/{sys_v}V", "pc", 1, inverter_cost)

    # 9. Changeover switch
    cs_a = 32 if sys_v == 48 else 16
    add(f"Changeover Switch {cs_a}A", "pc", 1, 55000)

    # 10. Battery cage / enclosure
    add("Battery Cage / Enclosure", "pc", 1, 120000)

    # 11. Accessories
    add("Cables, Lugs, Cable Ties & Accessories", "lot", 1, 80000)

    # 12. Labour & transport
    if labour_transport > 0:
        add("Labour & Transport", "lot", 1, labour_transport)

    return items
