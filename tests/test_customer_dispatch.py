"""
Tests for utils.customer_dispatch, the one place customer-facing documents
(quotations, receipts) are sent over email and WhatsApp.

Regression origin: receipts were email-only while quotations had WhatsApp, so
a customer with a phone but no email on file got nothing, and the flash
claimed a send that never happened.

Every sender is mocked. Never call the real ones from a test: this Mac shares
the production WhatsApp bridge, so a real send reaches a real customer.
"""
from unittest.mock import MagicMock, patch

import pytest

import utils.customer_dispatch as cd

PDF = b"%PDF-1.4 fake"


@pytest.fixture
def wa():
    with patch.object(cd, "send_document_whatsapp", return_value=(True, "")) as m:
        yield m


def _dispatch(email, phone, send_email=None, pdf=PDF):
    send_email = send_email or MagicMock(return_value=True)
    msg, cat = cd.dispatch_to_customer("Receipt", "RCT-2026-001", "Test Customer",
                                       email, phone, pdf, ["line one"], send_email)
    return msg, cat, send_email


class TestDispatchToCustomer:

    def test_phone_only_goes_out_on_whatsapp(self, wa):
        # the exact case that failed: phone on file, no email
        msg, cat, send_email = _dispatch("", "+15555550100")
        send_email.assert_not_called()
        wa.assert_called_once()
        assert wa.call_args.args[0] == "+15555550100"
        assert wa.call_args.args[2] == PDF
        assert "sent on WhatsApp" in msg and cat == "info"

    def test_both_contacts_caption_mentions_the_email(self, wa):
        msg, cat, send_email = _dispatch("a@example.com", "+15555550100")
        send_email.assert_called_once_with("a@example.com")
        caption = wa.call_args.args[3]
        assert "line one" in caption
        assert "sent to your email: a@example.com" in caption
        assert cat == "info"

    def test_caption_does_not_claim_an_email_that_failed(self, wa):
        msg, cat, _ = _dispatch("a@example.com", "+15555550100",
                                send_email=MagicMock(return_value=False))
        assert "your email" not in wa.call_args.args[3]
        assert "email to a@example.com FAILED" in msg
        assert cat == "warning"

    def test_whatsapp_failure_is_reported_not_hidden(self):
        with patch.object(cd, "send_document_whatsapp", return_value=(False, "no usable number")):
            msg, cat, _ = _dispatch("", "123")
        assert "WhatsApp send FAILED (no usable number)" in msg
        assert cat == "warning"

    def test_no_contacts_sends_nothing_and_says_so(self, wa):
        msg, cat, send_email = _dispatch("", "")
        send_email.assert_not_called()
        wa.assert_not_called()
        assert "nothing was sent" in msg and cat == "warning"

    def test_no_pdf_sends_nothing(self, wa):
        msg, cat, send_email = _dispatch("a@example.com", "+15555550100", pdf=None)
        send_email.assert_not_called()
        wa.assert_not_called()
        assert "NOT sent" in msg and cat == "warning"


class TestDispatchReceipt:

    RECEIPT = {"receipt_no": "RCT-2026-001", "customer_name": "Test Customer",
               "customer_phone": "+15555550100", "customer_email": "",
               "amount_paid": 1000000, "balance": 0, "payment_method": "Mobile Money"}

    def test_phone_only_receipt_builds_pdf_and_whatsapps_it(self, wa):
        with patch.object(cd, "build_receipt_pdf", return_value=PDF) as build, \
             patch.object(cd, "send_receipt_to_customer") as email:
            msg, cat = cd.dispatch_receipt(dict(self.RECEIPT))
        build.assert_called_once()          # previously skipped when no email
        email.assert_not_called()
        caption = wa.call_args.args[3]
        assert "Payment Receipt RCT-2026-001" in caption
        assert "UGX 1,000,000" in caption and "Fully settled" in caption
        assert cat == "info"

    def test_outstanding_balance_is_in_the_caption(self, wa):
        r = dict(self.RECEIPT, balance=250000)
        with patch.object(cd, "build_receipt_pdf", return_value=PDF):
            cd.dispatch_receipt(r)
        assert "Balance outstanding: UGX 250,000" in wa.call_args.args[3]

    def test_receipt_with_no_contacts_does_not_build_a_pdf(self, wa):
        r = dict(self.RECEIPT, customer_phone="", customer_email="")
        with patch.object(cd, "build_receipt_pdf") as build:
            msg, cat = cd.dispatch_receipt(r)
        build.assert_not_called()
        wa.assert_not_called()
        assert cat == "warning"


def test_notify_receipt_no_longer_sends_to_the_customer():
    # the internal notification must not double-send now that the route
    # dispatches the customer copy itself
    import utils.notify as n
    r = dict(TestDispatchReceipt.RECEIPT, customer_email="a@example.com", id="x")
    with patch.object(n, "_send_telegram"), patch.object(n, "_send_email"), \
         patch.object(n, "send_receipt_to_customer") as customer, \
         patch.object(n.threading, "Thread") as thread:
        n.notify_receipt(r)
        thread.call_args.kwargs["target"]()      # run the background job inline
    customer.assert_not_called()


def test_quotation_escaping_happens_once_and_only_where_html_is_rendered():
    # the flash is rendered |safe, the email body is HTML, the WhatsApp caption
    # is plain text: each must get exactly the escaping its medium needs
    import app
    q = {"quotation_no": "QT-1", "customer_name": "A & B <x>", "total_amount": 1000,
         "customer_email": "a@example.com", "customer_phone": "+15555550100"}
    with patch.object(cd, "send_document_whatsapp", return_value=(True, "")) as wa, \
         patch.object(app, "send_quotation_to_customer", return_value=True) as email:
        msg, cat = app._dispatch_quotation_to_customer(q, PDF, "Pending")
    assert "A &amp; B &lt;x&gt;" in msg and "&amp;amp;" not in msg   # flash: once
    assert email.call_args.args[1] == "A & B <x>"   # sender escapes inside its HTML body
    assert "Customer: A & B <x>" in wa.call_args.args[3]   # caption: raw text
    assert cat == "info"


def test_receipt_email_body_escapes_but_subject_and_filename_stay_raw():
    import utils.notify as n
    with patch.object(n, "_GMAIL_PASS", "x"), patch.object(n, "_smtp_send", return_value=True) as smtp:
        assert n.send_receipt_to_customer("RCT-1&2", "A & B <x>", 1000, 0, "Cash",
                                          "a@example.com", PDF) is True
    to, subject, html = smtp.call_args.args[:3]
    assert "A &amp; B &lt;x&gt;" in html and "A & B <x>" not in html
    assert subject.startswith("Payment Receipt RCT-1&2 ")
    assert smtp.call_args.kwargs["attachments"][0]["filename"] == "RCT-1&2.pdf"
