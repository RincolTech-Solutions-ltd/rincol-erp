"""
Send a customer-facing document to the customer over email and WhatsApp,
synchronously, and report what actually happened.

Every document type goes through dispatch_to_customer() so a new one cannot
ship email-only by accident. Receipts did exactly that until 2026-10-03 while
quotations already had WhatsApp, and a customer with a phone but no email on
file got nothing at all.

Returned messages are PLAIN TEXT. Callers rendering them as HTML (the Flask
flash, shown with |safe in base.html) must escape them first.
"""
import os


from utils.notify import send_customer_statement, send_receipt_to_customer
from utils.pdf import build_receipt_pdf, build_statement_pdf
from utils.whatsapp import send_document_whatsapp

_SIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "static", "img", "signature.png")


def load_default_sig():
    """Return signature bytes if the file exists, else None."""
    try:
        with open(_SIG_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def dispatch_to_customer(doc_label: str, doc_no: str, client: str,
                         email: str, phone: str, pdf_bytes: bytes,
                         caption_lines: list, send_email, file_stem: str = None) -> tuple:
    """Email then WhatsApp the PDF to whichever contacts are on file.

    send_email: callable(email_address) -> bool, the document's own email sender.
    caption_lines: the WhatsApp caption, plain text; an "also emailed" line is
    appended when the email went through.
    file_stem: the PDF's filename on WhatsApp, if it should differ from doc_no.
    Returns (plain_text_message, flash_category).
    """
    email = (email or "").strip()
    phone = (phone or "").strip()

    if not email and not phone:
        return (f"No email or phone on file for {client}, so {doc_label.lower()} {doc_no} "
                f"was not sent; nothing was sent to the customer."), "warning"
    if not pdf_bytes:
        return f"⚠️ PDF generation failed, {doc_label.lower()} {doc_no} was NOT sent to {client}.", "warning"

    email_ok = bool(send_email(email)) if email else False

    wa_ok, wa_msg = False, ""
    if phone:
        lines = list(caption_lines)
        if email_ok:
            lines.append(f"\nThe same has been sent to your email: {email}")
        wa_ok, wa_msg = send_document_whatsapp(phone, file_stem or doc_no, pdf_bytes, "\n".join(lines))

    parts = []
    if email:
        parts.append(f"emailed to {email}" if email_ok else f"email to {email} FAILED")
    if phone:
        parts.append("sent on WhatsApp" if wa_ok else f"WhatsApp send FAILED ({wa_msg})")

    all_ok = (not email or email_ok) and (not phone or wa_ok)
    icon = "📎" if (email_ok or wa_ok) else "⚠️"
    return (f"{icon} {doc_label} {doc_no} for {client}: " + "; ".join(parts) + ".",
            "info" if all_ok else "warning")


def dispatch_receipt(r: dict) -> tuple:
    """Build the receipt PDF and send it to the customer. See dispatch_to_customer."""
    rno     = r.get("receipt_no") or "-"
    client  = (r.get("customer_name") or "").strip()
    paid    = float(r.get("amount_paid") or 0)
    balance = float(r.get("balance") or 0)
    method  = r.get("payment_method") or "Cash"
    email   = (r.get("customer_email") or "").strip()
    phone   = (r.get("customer_phone") or "").strip()

    pdf_bytes = None
    if email or phone:
        try:
            pdf_bytes = build_receipt_pdf(r, sig_issued_bytes=load_default_sig())
        except Exception as e:
            print(f"[RECEIPT] PDF build FAILED for {rno}: {e}", flush=True)

    bal_line = "Fully settled, thank you!" if balance <= 0 else f"Balance outstanding: UGX {balance:,.0f}"
    caption = [
        f"*Rincol Tech Solutions Ltd*: Payment Receipt {rno}",
        f"Customer: {client}",
        f"Amount paid: UGX {paid:,.0f} ({method})",
        bal_line,
        "Thank you for your payment.",
    ]
    return dispatch_to_customer(
        "Receipt", rno, client, email, phone, pdf_bytes, caption,
        lambda to: send_receipt_to_customer(rno, client, paid, balance, method, to, pdf_bytes))


def dispatch_statement(customer: dict, quotations: list, stats: dict, statement_url: str) -> tuple:
    """Build the account statement PDF and send it to the customer. See dispatch_to_customer."""
    name    = (customer.get("name") or "").strip()
    cust_no = customer.get("customer_no") or "-"
    email   = (customer.get("email") or "").strip()
    phone   = (customer.get("phone") or "").strip()
    owed    = float(stats.get("total_outstanding") or 0)

    pdf_bytes = None
    if email or phone:
        try:
            pdf_bytes = build_statement_pdf(customer, quotations, stats)
        except Exception as e:
            print(f"[STATEMENT] PDF build FAILED for {cust_no}: {e}", flush=True)

    caption = [
        f"*Rincol Tech Solutions Ltd*: Account Statement {cust_no}",
        f"Customer: {name}",
        f"Outstanding: UGX {owed:,.0f}" if owed > 0 else "Your account is fully settled, thank you!",
        f"View your live statement any time: {statement_url}",
    ]
    return dispatch_to_customer(
        "Statement", cust_no, name, email, phone, pdf_bytes, caption,
        lambda to: send_customer_statement(customer, stats, pdf_bytes, statement_url, to),
        file_stem=f"Statement_{cust_no}")
