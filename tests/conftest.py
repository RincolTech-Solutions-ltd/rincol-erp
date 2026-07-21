"""
Shared fixtures for the Rincol ERP test suite.

DB calls are mocked at the utils.db module level — tests never touch the
live Supabase instance.  Auth is satisfied by injecting a fake session.
"""
import sys
import uuid
import pytest
from unittest.mock import MagicMock, patch

# ── Stub out supabase before any app import so the module resolves ─────────────
_supabase_stub = MagicMock()
_supabase_stub.create_client.return_value = MagicMock()
sys.modules.setdefault("supabase", _supabase_stub)
sys.modules.setdefault("supabase.client", _supabase_stub)

# Stub psycopg2 pool so importing utils.db doesn't attempt a real connection
_psycopg2_stub = MagicMock()
_psycopg2_stub.extras.RealDictCursor = MagicMock()
_psycopg2_stub.pool.ThreadedConnectionPool = MagicMock()
sys.modules.setdefault("psycopg2", _psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", _psycopg2_stub.extras)
sys.modules.setdefault("psycopg2.pool", _psycopg2_stub.pool)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(**kwargs):
    """Return a dict-like object that also supports attribute access, mirroring
    psycopg2 RealDictRow behaviour used throughout app.py."""
    d = dict(**kwargs)
    d["get"] = d.get        # make .get() work so dict and RealDictRow are compatible
    return d


FAKE_CUSTOMER = _row(
    id="aaaaaaaa-0000-0000-0000-000000000001",
    customer_no="CUST-0001",
    name="Test Customer",
    phone="0701234567",
    email="test@example.com",
    address="Kampala",
)

FAKE_CUSTOMERS = [FAKE_CUSTOMER]

# JUSTIFICATION-A3: solar_sizings has 55 columns; all are accessed by the Jinja template — every field is required.
FAKE_SIZING = _row(
    id="sz-0001", client_name="Test Customer", client_phone="0701234567",
    client_email="test@example.com", client_site="Kigo",
    customer_id="aaaaaaaa-0000-0000-0000-000000000001",
    system_voltage=48, battery_type="Li-ion", quotation_id=None, bom_locked=False,
    utility_provider="UMEME", utility_tariff=900, tariff_escalation=5,
    payback_years=4.5, system_cost=5000000, maintenance_cost_10yr=500000,
    solar_cost_per_kwh=150, yaka_savings_10yr=8000000,
    peak_sun_hours=5.5, performance_ratio=0.75, days_autonomy=1, dod=0.8,
    inverter_efficiency=0.9, cable_efficiency=0.97, inverter_idle_w=50,
    panel_wp=550, panel_voc=40.0, panel_isc=10.0, panel_cost=420000,
    mppt_trackers=1, mppt_min_v=100, mppt_max_v=450, max_oc_v=500,
    max_input_current_per_tracker=20, max_isc_per_tracker=20, max_pv_power_per_tracker=6000,
    battery_ah=200, battery_voltage=48.0, battery_cost_each=3000000, battery_is_bank=True,
    inverter_kw=3.5, inverter_cost=1500000, labour_transport=500000,
    total_daily_wh=2000, inverter_idle_wh=120, peak_load_w=800, battery_ah_min=400,
    batteries_in_series=1, batteries_in_parallel=2, total_batteries=2,
    required_wp=1200, panels_by_energy=3, panels_by_voltage=2,
    panels_in_series=1, strings_total=3, strings_per_tracker=3,
    panels_recommended=3, voltage_override=False, annual_yield_kwh=730,
    inverter_flag=False, panel_array_flag=False,
    status="Draft", notes="", created_at="2026-01-01", updated_at="2026-01-01",
)


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create application with test config. Supabase and psycopg2 are stubbed
    at module level above so no network calls occur on import."""
    import app as flask_app
    flask_app.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )
    return flask_app.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def authed_client(client):
    """Test client with a logged-in session."""
    with client.session_transaction() as sess:
        sess["user"] = {"id": "usr-1", "email": "hillary@rincol.com"}
    return client
