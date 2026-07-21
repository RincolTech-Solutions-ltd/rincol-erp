"""
Tests for the solar sizing customer FK feature.

Covers:
  - GET /solar/new     — customers list injected into template
  - POST /solar/new    without customer_id — validation rejects
  - POST /solar/new    with customer_id    — saves and redirects
  - _save_sizing       — resolves name/phone/email from customers table
  - GET /solar/<id>/edit  — customers list injected
  - POST /solar/<id>/to-quotation — customer_id forwarded to quotation
"""
from unittest.mock import patch, MagicMock

import pytest
from werkzeug.datastructures import ImmutableMultiDict

from tests.conftest import FAKE_CUSTOMER, FAKE_CUSTOMERS, FAKE_SIZING

# app imports query/execute directly, so patches must target 'app.query' etc.
_Q  = "app.query"
_Q1 = "app.query_one"
_EX = "app.execute"


# ── Form helpers ──────────────────────────────────────────────────────────────

def _form(**overrides):
    """Base valid solar sizing form as ImmutableMultiDict (supports getlist)."""
    base = {
        "customer_id":       "aaaaaaaa-0000-0000-0000-000000000001",
        "client_site":       "Kigo",
        "system_voltage":    "48",
        "battery_type":      "Li-ion",
        "peak_sun_hours":    "5.5",
        "days_autonomy":     "1",
        "dod":               "0.8",
        "inverter_efficiency": "0.9",
        "cable_efficiency":  "0.97",
        "inverter_idle_w":   "50",
        "performance_ratio": "0.75",
        "panel_wp":          "550",
        "panel_voc":         "40",
        "panel_isc":         "10",
        "panel_cost":        "420000",
        "mppt_trackers":     "1",
        "mppt_min_v":        "100",
        "mppt_max_v":        "450",
        "max_oc_v":          "500",
        "max_input_current_per_tracker": "20",
        "max_isc_per_tracker": "20",
        "max_pv_power_per_tracker": "6000",
        "battery_ah":        "200",
        "battery_voltage":   "48",
        "battery_cost_each": "3000000",
        "battery_is_bank":   "true",
        "inverter_kw":       "3.5",
        "inverter_cost":     "1500000",
        "labour_transport":  "500000",
        "utility_provider":  "UMEME",
        "utility_tariff":    "900",
        "tariff_escalation": "5",
        "notes":             "",
    }
    base.update(overrides)
    return ImmutableMultiDict(base.items())


def _route_query(extra_customers=None):
    """Query mock that routes by SQL fragment so catalog/customer calls don't collide."""
    customers = extra_customers if extra_customers is not None else FAKE_CUSTOMERS

    def _q(sql, params=None):
        if "FROM customers" in sql:
            return customers
        if "catalog_items" in sql:
            return []
        return []

    return _q


# ── GET /solar/new ────────────────────────────────────────────────────────────

class TestSolarNewGet:
    def test_redirects_unauthenticated(self, client):
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = client.get("/solar/new")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_returns_200_for_authenticated(self, authed_client):
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.get("/solar/new")
        assert resp.status_code == 200

    def test_customer_dropdown_rendered(self, authed_client):
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.get("/solar/new")
        body = resp.data.decode()
        assert "CUST-0001" in body
        assert "Test Customer" in body
        assert 'id="sc_hidden"' in body

    def test_add_customer_link_present(self, authed_client):
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.get("/solar/new")
        assert b"Add customer" in resp.data

    def test_all_customers_appear_in_page(self, authed_client):
        two = list(FAKE_CUSTOMERS) + [dict(
            FAKE_CUSTOMER,
            id="bbbbbbbb-0000-0000-0000-000000000002",
            customer_no="CUST-0002",
            name="Another Person",
        )]
        with patch(_Q, _route_query(two)), patch(_Q1, return_value=None):
            resp = authed_client.get("/solar/new")
        body = resp.data.decode()
        assert "CUST-0001" in body
        assert "CUST-0002" in body


# ── POST /solar/new — validation ──────────────────────────────────────────────

class TestSolarNewPostValidation:
    def test_missing_customer_id_stays_on_form(self, authed_client):
        data = {k: v for k, v in _form().items() if k != "customer_id"}
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.post("/solar/new", data=data)
        assert resp.status_code == 200

    def test_missing_customer_id_shows_error_message(self, authed_client):
        data = {k: v for k, v in _form().items() if k != "customer_id"}
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.post("/solar/new", data=data, follow_redirects=True)
        assert "customer" in resp.data.decode().lower()

    def test_empty_customer_id_stays_on_form(self, authed_client):
        data = dict(_form(), customer_id="")
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.post("/solar/new", data=data)
        assert resp.status_code == 200

    def test_missing_customer_does_not_redirect_to_solar_view(self, authed_client):
        data = {k: v for k, v in _form().items() if k != "customer_id"}
        with patch(_Q, _route_query()), patch(_Q1, return_value=None):
            resp = authed_client.post("/solar/new", data=data)
        assert resp.status_code != 302


# ── POST /solar/new — happy path ──────────────────────────────────────────────

class TestSolarNewPostSuccess:
    def _setup_mocks(self, executed):
        def fake_query(sql, params=None):
            if "FROM customers" in sql:
                return FAKE_CUSTOMERS
            return []   # catalog_items, bom, appliances, etc.

        def fake_query_one(sql, params=None):
            if "FROM customers WHERE id" in sql:
                return FAKE_CUSTOMER
            return None

        def fake_execute(sql, params=None):
            executed.append((sql, list(params) if params else []))

        return fake_query, fake_query_one, fake_execute

    def test_valid_post_redirects_to_view(self, authed_client):
        executed = []
        fq, fq1, fex = self._setup_mocks(executed)
        with patch(_Q, fq), patch(_Q1, fq1), patch(_EX, fex):
            resp = authed_client.post("/solar/new", data=dict(_form()))
        assert resp.status_code == 302
        assert "/solar/" in resp.headers["Location"]

    def test_valid_post_inserts_solar_sizing(self, authed_client):
        executed = []
        fq, fq1, fex = self._setup_mocks(executed)
        with patch(_Q, fq), patch(_Q1, fq1), patch(_EX, fex):
            authed_client.post("/solar/new", data=dict(_form()))
        sqls = [sql for sql, _ in executed]
        assert any("INSERT INTO solar_sizings" in s for s in sqls)

    def test_valid_post_stores_customer_id(self, authed_client):
        executed = []
        fq, fq1, fex = self._setup_mocks(executed)
        with patch(_Q, fq), patch(_Q1, fq1), patch(_EX, fex):
            authed_client.post("/solar/new", data=dict(_form()))
        sizing_params = [p for sql, p in executed if "INSERT INTO solar_sizings" in sql]
        assert sizing_params, "solar_sizings INSERT not executed"
        assert FAKE_CUSTOMER["id"] in sizing_params[0]

    def test_valid_post_stores_resolved_client_name(self, authed_client):
        executed = []
        fq, fq1, fex = self._setup_mocks(executed)
        with patch(_Q, fq), patch(_Q1, fq1), patch(_EX, fex):
            authed_client.post("/solar/new", data=dict(_form()))
        sizing_params = [p for sql, p in executed if "INSERT INTO solar_sizings" in sql]
        assert "Test Customer" in sizing_params[0]


# ── _save_sizing: customer resolution unit tests ──────────────────────────────

class TestSaveSizingCustomerResolution:
    """Call _save_sizing directly with a fake ImmutableMultiDict."""

    def _run(self, form, q1_return, app_fixture):
        executed = []

        def fake_query(sql, params=None):
            if "bom_locked" in sql:
                return []
            if "catalog_items" in sql:
                return []
            return []

        def fake_execute(sql, params=None):
            executed.append((sql, list(params) if params else []))

        with app_fixture.test_request_context():
            with patch(_Q,  fake_query), \
                 patch(_Q1, q1_return), \
                 patch(_EX, fake_execute):
                import app as flask_app
                flask_app._save_sizing("sz-unit", form)

        return [p for sql, p in executed if "INSERT INTO solar_sizings" in sql]

    def test_client_name_resolved_from_customer(self, app):
        form = _form(**{"client_name": "WRONG NAME"})
        params = self._run(form, lambda s, p=None: FAKE_CUSTOMER if "FROM customers WHERE id" in s else None, app)
        assert params, "solar_sizings INSERT not found"
        assert "Test Customer" in params[0]
        assert "WRONG NAME" not in params[0]

    def test_phone_resolved_from_customer(self, app):
        form = _form(**{"client_phone": "WRONG"})
        params = self._run(form, lambda s, p=None: FAKE_CUSTOMER if "FROM customers WHERE id" in s else None, app)
        assert "0701234567" in params[0]
        assert "WRONG" not in params[0]

    def test_email_resolved_from_customer(self, app):
        form = _form(**{"client_email": "wrong@bad.com"})
        params = self._run(form, lambda s, p=None: FAKE_CUSTOMER if "FROM customers WHERE id" in s else None, app)
        assert "test@example.com" in params[0]

    def test_customer_id_stored_in_insert(self, app):
        form = _form()
        params = self._run(form, lambda s, p=None: FAKE_CUSTOMER if "FROM customers WHERE id" in s else None, app)
        assert FAKE_CUSTOMER["id"] in params[0]

    def test_no_customer_id_falls_back_to_form_values(self, app):
        form = _form(**{"customer_id": "", "client_name": "Walk-in"})
        params = self._run(form, lambda s, p=None: None, app)
        assert params
        assert "Walk-in" in params[0]


# ── GET /solar/<id>/edit ──────────────────────────────────────────────────────

class TestSolarEdit:
    def _mocks(self):
        def fake_query(sql, params=None):
            if "FROM customers" in sql:
                return FAKE_CUSTOMERS
            return []   # appliances, catalog_items, bom, etc.

        def fake_query_one(sql, params=None):
            if "FROM solar_sizings" in sql:
                return FAKE_SIZING
            return None

        return fake_query, fake_query_one

    def test_edit_returns_200(self, authed_client):
        fq, fq1 = self._mocks()
        with patch(_Q, fq), patch(_Q1, fq1):
            resp = authed_client.get("/solar/sz-0001/edit")
        assert resp.status_code == 200

    def test_edit_injects_customers(self, authed_client):
        fq, fq1 = self._mocks()
        with patch(_Q, fq), patch(_Q1, fq1):
            resp = authed_client.get("/solar/sz-0001/edit")
        assert "CUST-0001" in resp.data.decode()

    def test_edit_embeds_current_customer_id(self, authed_client):
        fq, fq1 = self._mocks()
        with patch(_Q, fq), patch(_Q1, fq1):
            resp = authed_client.get("/solar/sz-0001/edit")
        assert FAKE_CUSTOMER["id"] in resp.data.decode()

    def test_edit_post_missing_customer_stays_on_form(self, authed_client):
        fq, fq1 = self._mocks()
        data = {k: v for k, v in _form().items() if k != "customer_id"}
        with patch(_Q, fq), patch(_Q1, fq1), patch(_EX, lambda s, p=None: None):
            resp = authed_client.post("/solar/sz-0001/edit", data=data)
        assert resp.status_code == 200

    def test_unauthenticated_edit_redirects(self, client):
        with patch(_Q, return_value=[]), patch(_Q1, return_value=None):
            resp = client.get("/solar/sz-0001/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ── POST /solar/<id>/to-quotation ─────────────────────────────────────────────

class TestSolarToQuotation:
    def _run(self, authed_client):
        executed = []

        def fake_query(sql, params=None):
            if "solar_sizing_bom" in sql:
                return []
            return []

        def fake_query_one(sql, params=None):
            if "FROM solar_sizings" in sql:
                return FAKE_SIZING
            if "qt_year" in sql:
                return {"value": "2026"}
            if "qt_counter" in sql:
                return {"value": "5"}
            return None

        def fake_execute(sql, params=None):
            executed.append((sql, list(params) if params else []))

        with patch(_Q, fake_query), \
             patch(_Q1, fake_query_one), \
             patch(_EX, fake_execute):
            resp = authed_client.post("/solar/sz-0001/to-quotation")

        return resp, executed

    def test_redirects_after_creating_quotation(self, authed_client):
        resp, _ = self._run(authed_client)
        assert resp.status_code == 302

    def test_quotation_insert_executed(self, authed_client):
        _, executed = self._run(authed_client)
        sqls = [sql for sql, _ in executed]
        assert any("INSERT INTO quotations" in s for s in sqls)

    def test_quotation_receives_customer_id(self, authed_client):
        _, executed = self._run(authed_client)
        q_params = [p for sql, p in executed if "INSERT INTO quotations" in sql]
        assert q_params
        assert FAKE_CUSTOMER["id"] in q_params[0]

    def test_quotation_title_includes_client_name(self, authed_client):
        _, executed = self._run(authed_client)
        q_params = [p for sql, p in executed if "INSERT INTO quotations" in sql][0]
        title = next(p for p in q_params if isinstance(p, str) and "Solar" in p)
        assert "Test Customer" in title

    def test_sizing_quotation_id_updated(self, authed_client):
        _, executed = self._run(authed_client)
        sqls = [sql for sql, _ in executed]
        assert any("UPDATE solar_sizings" in s for s in sqls)

    def test_unauthenticated_to_quotation_redirects(self, client):
        with patch(_Q, return_value=[]), patch(_Q1, return_value=None):
            resp = client.post("/solar/sz-0001/to-quotation")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
