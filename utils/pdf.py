"""PDF generation — matching Rincol Tech Solutions desktop app design."""
import io
import os
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, Image, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from PIL import Image as PILImage

HEADER_IMG_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "img", "letterhead.png")
LOGO_PATH       = os.path.join(os.path.dirname(__file__), "..", "static", "img", "rincol_logo.png")

# Brand colours
BLUE      = colors.HexColor("#00aced")   # primary blue — header row, banners
LBLUE     = colors.HexColor("#eef2ff")   # light blue — alternating rows, customer block
DARK      = colors.HexColor("#1a1a2e")   # dark navy — quotation title banner
LGRAY     = colors.HexColor("#f5f5f5")   # light grey — receipt alternating rows
GREY_LINE = colors.HexColor("#cccccc")   # border / grid lines
LGREEN    = colors.HexColor("#dcfce7")   # receipt balance row highlight
WHITE     = colors.white
BLACK     = colors.black
DGRAY     = colors.HexColor("#333333")


def _ps(name, **kw):
    return ParagraphStyle(name, **kw)


def _qr_image(url: str, size: float):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=size, height=size)


def _sig_image(path_or_bytes, max_w=2.0 * cm, max_h=2.0 * cm):
    if not path_or_bytes:
        return None
    try:
        if isinstance(path_or_bytes, (str, os.PathLike)):
            pil = PILImage.open(path_or_bytes)
        else:
            pil = PILImage.open(io.BytesIO(path_or_bytes))
        pw, ph = pil.size
        ratio = min(max_w / pw, max_h / ph)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=pw * ratio, height=ph * ratio)
    except Exception:
        return None


def _logo_image(max_w=4.0 * cm, max_h=1.14 * cm):
    if not os.path.exists(LOGO_PATH):
        return None
    try:
        pil = PILImage.open(LOGO_PATH)
        pw, ph = pil.size
        ratio = min(max_w / pw, max_h / ph)
        img = Image(LOGO_PATH, width=pw * ratio, height=ph * ratio)
        img.hAlign = "LEFT"
        return img
    except Exception:
        return None


def _letterhead(W):
    if os.path.exists(HEADER_IMG_PATH):
        img_h = W * (157 / 1216)
        return Image(HEADER_IMG_PATH, width=W, height=img_h)
    return Paragraph(
        "RINCOL TECH SOLUTIONS LTD",
        _ps("hfb", fontSize=17, fontName="Helvetica-Bold", textColor=BLUE),
    )


def number_to_words(n: float) -> str:
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
            "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
            "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty",
            "Seventy", "Eighty", "Ninety"]

    def _below_1000(x):
        if x < 20:
            return ones[x]
        if x < 100:
            return tens[x // 10] + (" " + ones[x % 10] if x % 10 else "")
        return ones[x // 100] + " Hundred" + (
            " and " + _below_1000(x % 100) if x % 100 else ""
        )

    n = int(round(n))
    if n == 0:
        return "Zero"
    parts = []
    billions  = n // 1_000_000_000
    millions  = (n % 1_000_000_000) // 1_000_000
    thousands = (n % 1_000_000) // 1_000
    remainder = n % 1_000
    if billions:  parts.append(_below_1000(billions)  + " Billion")
    if millions:  parts.append(_below_1000(millions)  + " Million")
    if thousands: parts.append(_below_1000(thousands) + " Thousand")
    if remainder: parts.append(_below_1000(remainder))
    return " ".join(parts)


def _amount_words(amount: float) -> str:
    n = int(round(amount))
    if n == 0:
        return "Zero Shillings Only"
    return number_to_words(n) + " Shillings Only"


# ── Quotation PDF ─────────────────────────────────────────────────────────────

def build_quotation_pdf(q: dict, items: list, sig_bytes=None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    W = A4[0] - 3.6 * cm
    elems = []

    # Paragraph styles
    meta_r   = _ps("mr",   fontSize=9,  fontName="Helvetica-Bold",  textColor=BLUE,  alignment=TA_RIGHT)
    title_s  = _ps("ttl",  fontSize=13, fontName="Helvetica-Bold",  textColor=WHITE, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4)
    val_s    = _ps("val",  fontSize=9,  fontName="Helvetica",        textColor=BLACK)
    hdr_c    = _ps("hc",   fontSize=9,  fontName="Helvetica-Bold",  textColor=WHITE, alignment=TA_CENTER)
    hdr_l    = _ps("hl",   fontSize=9,  fontName="Helvetica-Bold",  textColor=WHITE, alignment=TA_LEFT)
    tot_s    = _ps("tot",  fontSize=10, fontName="Helvetica-Bold",  textColor=WHITE, alignment=TA_RIGHT)
    cell_s   = _ps("cell", fontSize=9,  fontName="Helvetica",        textColor=BLACK)
    cell_r   = _ps("cellr",fontSize=9,  fontName="Helvetica",        textColor=BLACK, alignment=TA_RIGHT)
    cell_c   = _ps("cellc",fontSize=9,  fontName="Helvetica",        textColor=BLACK, alignment=TA_CENTER)
    blue_head= _ps("bh",   fontSize=10, fontName="Helvetica-Bold",  textColor=BLUE)
    reg_val  = _ps("rv",   fontSize=9,  fontName="Helvetica",        textColor=BLACK)
    note_s   = _ps("note", fontSize=8,  fontName="Helvetica",        textColor=DGRAY, leading=13, leftIndent=10)
    foot_s   = _ps("foot", fontSize=7,  fontName="Helvetica",        textColor=colors.HexColor("#888888"), alignment=TA_CENTER)
    sig_s    = _ps("sig",  fontSize=9,  fontName="Helvetica",        textColor=DGRAY)

    # 1. Letterhead
    elems.append(_letterhead(W))
    elems.append(Spacer(1, 4))

    # 2. Quotation No + Date (right-aligned, bold blue)
    qno   = q.get("quotation_no", "")
    qdate = q.get("date", "")
    meta_tbl = Table([[Paragraph(
        f"<b>Quotation No.:</b>&nbsp;&nbsp;{qno}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Date:</b>&nbsp;&nbsp;{qdate}", meta_r
    )]], colWidths=[W])
    meta_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    elems.append(meta_tbl)
    elems.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=6, spaceBefore=4))

    # 3. Title banner (dark bg, white text)
    title_text = q.get("title", "Quotation").upper()
    title_tbl = Table([[Paragraph(title_text, title_s)]], colWidths=[W])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(title_tbl)
    elems.append(Spacer(1, 6))

    # 4. Customer block (single cell, LBLUE bg)
    cname  = q.get("customer_name", "")
    cphone = q.get("customer_phone", "")
    cemail = q.get("customer_email", "")
    caddr  = q.get("customer_address", "")
    cust_lines = f"<b>Attn:</b> {cname}<br/><b>Phone:</b> {cphone}"
    if cemail:
        cust_lines += f"<br/><b>Email:</b> {cemail}"
    if caddr:
        cust_lines += f"<br/><b>Location:</b> {caddr}"
    cust_tbl = Table([[Paragraph(cust_lines, val_s)]], colWidths=[W])
    cust_tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, GREY_LINE),
        ("BACKGROUND",    (0, 0), (-1, -1), LBLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    elems.append(cust_tbl)
    elems.append(Spacer(1, 10))

    # 5. Line items table — No. | Description | Qty | Unit Price (UGX) | Total (UGX)
    tbl_data = [[
        Paragraph("No.",               hdr_c),
        Paragraph("Description",       hdr_l),
        Paragraph("Qty",               hdr_c),
        Paragraph("Unit Price (UGX)",  hdr_c),
        Paragraph("Total (UGX)",       hdr_c),
    ]]
    grand = 0.0
    for i, it in enumerate(items):
        qty_v   = float(it.get("qty", 0))
        price_v = float(it.get("unit_price", 0))
        total_v = float(it.get("total", qty_v * price_v))
        grand  += total_v
        qty_str = str(int(qty_v)) if qty_v == int(qty_v) else f"{qty_v:.2f}"
        tbl_data.append([
            Paragraph(str(it.get("line_no", i + 1)), cell_c),
            Paragraph(it.get("description", ""),      cell_s),
            Paragraph(qty_str,                         cell_c),
            Paragraph(f"{price_v:,.0f}",               cell_r),
            Paragraph(f"{total_v:,.0f}",               cell_r),
        ])

    n = len(tbl_data)  # index of next row (first total row)

    # Subtotal row
    tbl_data.append([
        Paragraph("", tot_s), Paragraph("", tot_s),
        Paragraph("SUBTOTAL", tot_s), Paragraph("", tot_s),
        Paragraph(f"UGX {grand:,.0f}", tot_s),
    ])
    subtotal_row = n

    # Grand total row
    tbl_data.append([
        Paragraph("", tot_s), Paragraph("", tot_s),
        Paragraph("GRAND TOTAL", tot_s), Paragraph("", tot_s),
        Paragraph(f"UGX {grand:,.0f}", tot_s),
    ])
    final_row = len(tbl_data) - 1

    col_w = [W * 0.06, W * 0.46, W * 0.08, W * 0.20, W * 0.20]
    items_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0),            (-1, 0),            BLUE),
        # Alternating data rows
        ("ROWBACKGROUNDS",(0, 1),            (-1, n - 1),        [WHITE, LBLUE]),
        # Subtotal row
        ("BACKGROUND",    (0, subtotal_row), (-1, subtotal_row), BLUE),
        ("SPAN",          (0, subtotal_row), (1, subtotal_row)),
        ("SPAN",          (2, subtotal_row), (3, subtotal_row)),
        # Grand total row
        ("BACKGROUND",    (0, final_row),    (-1, final_row),    BLUE),
        ("SPAN",          (0, final_row),    (1, final_row)),
        ("SPAN",          (2, final_row),    (3, final_row)),
        # Borders
        ("BOX",           (0, 0), (-1, -1),  0.5, GREY_LINE),
        ("INNERGRID",     (0, 0), (-1, -1),  0.3, GREY_LINE),
        # Padding
        ("TOPPADDING",    (0, 0), (-1, -1),  6),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
        ("LEFTPADDING",   (0, 0), (-1, -1),  6),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  6),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
    ]))
    elems.append(items_tbl)
    elems.append(Spacer(1, 10))

    # 6. Notes
    notes = (q.get("notes") or "").strip()
    if notes:
        note_elems = [Paragraph("<b>Notes</b>", blue_head), Spacer(1, 4)]
        for line in notes.splitlines():
            line = line.strip()
            if line:
                if not line.startswith("-"):
                    line = "- " + line
                note_elems.append(Paragraph(line, note_s))
        elems.append(KeepTogether(note_elems))
        elems.append(Spacer(1, 8))

    # 7. Terms & Conditions + Payment Channels
    delivery = (q.get("delivery") or "").strip()
    validity = (q.get("validity") or "30 days").strip()
    warranty = (q.get("warranty") or "").strip()
    payment  = (q.get("payment_terms") or "Cash / MM / EFT").strip()

    def bold_val(label, value):
        return Paragraph(f"<b>{label}:</b> {value}", reg_val)

    tc_elems = [
        Paragraph("<b>Terms &amp; Conditions</b>", blue_head),
        Spacer(1, 4),
    ]
    if delivery:
        tc_elems.append(bold_val("Delivery Period", delivery))
    if validity:
        tc_elems.append(bold_val("Validity", validity))
    tc_elems.append(bold_val("Payment", payment))
    tc_elems += [
        Paragraph("Payment Channels", reg_val),
        Paragraph("<b>MM</b>: 0775102684 – Arinda Hillary", reg_val),
        Paragraph("<b>BANK DETAILS:</b>", reg_val),
        Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;Bank Name: Stanbic Bank",      reg_val),
        Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;Account Name: Hillary Arinda",  reg_val),
        Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;Account No.: 9030023010355",    reg_val),
        Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;Branch: Ntinda",               reg_val),
    ]
    if warranty:
        tc_elems.append(bold_val("Warranty", warranty))
    elems.append(KeepTogether(tc_elems))
    elems.append(Spacer(1, 14))

    # 8. Signature
    elems.append(Paragraph("Signature:", sig_s))
    elems.append(Spacer(1, 6))
    sig_img = _sig_image(sig_bytes)
    if sig_img:
        sig_img.hAlign = "LEFT"
        elems.append(sig_img)
    else:
        elems.append(Spacer(1, 30))
    elems.append(HRFlowable(width=W * 0.35, thickness=0.8,
                             color=colors.HexColor("#888888"),
                             hAlign="LEFT", spaceAfter=6))
    logo = _logo_image()
    if logo:
        elems.append(logo)
    elems.append(Spacer(1, 10))

    # 9. Footer (text left, QR right)
    elems.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceBefore=8, spaceAfter=4))
    qr = _qr_image("https://www.rincoltech.com", 2 * cm)
    footer_tbl = Table([[
        Paragraph(
            "Rincol Tech Solutions Ltd  |  Power Backup &amp; Electrical Solutions  |  Kampala, Uganda<br/>"
            "www.rincoltech.com  |  Thank you for your business.",
            foot_s,
        ),
        qr,
    ]], colWidths=[W * 0.75, W * 0.25])
    footer_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",  (1, 0), (1, 0),   "RIGHT"),
    ]))
    elems.append(footer_tbl)

    doc.build(elems)
    return buf.getvalue()


# ── Receipt PDF ───────────────────────────────────────────────────────────────

def build_receipt_pdf(r: dict, sig_issued_bytes=None, sig_received_bytes=None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    W = A4[0] - 3.6 * cm
    elems = []

    # Paragraph styles
    meta_r  = _ps("mr",  fontSize=9,  fontName="Helvetica-Bold", textColor=BLUE,  alignment=TA_RIGHT)
    title_s = _ps("ttl", fontSize=16, fontName="Helvetica-Bold", textColor=BLUE,  alignment=TA_CENTER, spaceBefore=6, spaceAfter=6)
    lbl_s   = _ps("lbl", fontSize=9,  fontName="Helvetica-Bold", textColor=DGRAY)
    val_s   = _ps("val", fontSize=9,  fontName="Helvetica",       textColor=BLACK)
    sec_s   = _ps("sec", fontSize=10, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)
    cell_r  = _ps("cr",  fontSize=9,  fontName="Helvetica",       textColor=BLACK, alignment=TA_RIGHT)
    cell_b  = _ps("cb",  fontSize=9,  fontName="Helvetica-Bold", textColor=BLACK, alignment=TA_RIGHT)
    auth_s  = _ps("au",  fontSize=10, fontName="Helvetica-Bold", textColor=BLUE)
    sig_lbl = _ps("sl",  fontSize=9,  fontName="Helvetica",       textColor=DGRAY)
    foot_s  = _ps("ft",  fontSize=7,  fontName="Helvetica",       textColor=colors.HexColor("#888888"), alignment=TA_CENTER)

    border = ("BOX",      (0, 0), (-1, -1), 0.5, GREY_LINE)
    inner  = ("INNERGRID",(0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd"))
    pad    = ("PADDING",  (0, 0), (-1, -1), 7)

    # 1. Letterhead
    elems.append(_letterhead(W))
    elems.append(Spacer(1, 4))

    # 2. Receipt No + Date
    rno   = r.get("receipt_no", "")
    rdate = r.get("date", "")
    meta_tbl = Table([[Paragraph(
        f"<b>Receipt No.:</b>&nbsp;&nbsp;{rno}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Date:</b>&nbsp;&nbsp;{rdate}", meta_r
    )]], colWidths=[W])
    meta_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    elems.append(meta_tbl)
    elems.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=4, spaceBefore=4))

    # 3. Title (blue text, no dark banner)
    elems.append(Paragraph("RECEIPT", title_s))
    elems.append(Spacer(1, 6))

    # 4. Customer info rows
    cname  = r.get("customer_name", "")
    cphone = r.get("customer_phone", "")
    caddr  = r.get("customer_address", "")
    cust_str = cname
    if cphone: cust_str += f"  |  {cphone}"
    if caddr:  cust_str += f"  |  {caddr}"

    amount_fig  = float(r.get("amount_fig", 0))
    amount_paid = float(r.get("amount_paid", 0))
    balance     = float(r.get("balance") if r.get("balance") is not None else (amount_fig - amount_paid))
    prev_paid   = amount_fig - amount_paid - balance  # everything paid before this receipt

    info_rows = [
        [Paragraph("Received with thanks from:", lbl_s), Paragraph(cust_str, val_s)],
        [Paragraph("Amount in words:", lbl_s),            Paragraph(_amount_words(amount_paid), val_s)],
        [Paragraph("Being payment for:", lbl_s),          Paragraph((r.get("being_for") or "").replace("\n", "<br/>"), val_s)],
    ]
    info_tbl = Table(info_rows, colWidths=[W * 0.32, W * 0.68])
    info_tbl.setStyle(TableStyle([
        border, inner, pad,
        ("BACKGROUND", (0, 0), (0, -1), LBLUE),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(info_tbl)
    elems.append(Spacer(1, 10))

    # 5. PAYMENT DETAILS banner + rows
    pay_hdr = Table([[Paragraph("PAYMENT DETAILS", sec_s)]], colWidths=[W])
    pay_hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("PADDING",    (0, 0), (-1, -1), 7),
    ]))
    elems.append(pay_hdr)

    pay_rows = [
        [Paragraph("Amount in Figures (UGX)", lbl_s), Paragraph(f"{amount_fig:,.0f}", cell_r)],
    ]
    if prev_paid > 0:
        pay_rows.append([Paragraph("Previously Paid (UGX)", lbl_s), Paragraph(f"{prev_paid:,.0f}", cell_r)])
    pay_rows.append([Paragraph("This Payment (UGX)", lbl_s), Paragraph(f"{amount_paid:,.0f}", cell_r)])
    balance_row = len(pay_rows)
    pay_rows.append([Paragraph("Outstanding Balance (UGX)", lbl_s), Paragraph(f"{balance:,.0f}", cell_b)])

    pm_val = (r.get("payment_method") or "Cash").strip()
    pay_rows.append([Paragraph("Payment Method", lbl_s), Paragraph(pm_val, val_s)])

    cheque = (r.get("cheque_no") or "").strip()
    if cheque:
        pm = pm_val
        ref_label = "Transaction ID" if pm == "Mobile Money" else "Reference No." if pm == "Bank Transfer" else "Cheque No."
        pay_rows.append([Paragraph(ref_label, lbl_s), Paragraph(cheque, val_s)])

    pay_tbl = Table(pay_rows, colWidths=[W * 0.68, W * 0.32])
    pay_tbl.setStyle(TableStyle([
        border, inner, pad,
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LGRAY]),
        ("BACKGROUND",     (0, balance_row), (-1, balance_row), LGREEN),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(pay_tbl)
    elems.append(Spacer(1, 14))

    # 6. AUTHORISATION banner + two-column block
    auth_hdr = Table([[Paragraph("AUTHORISATION", sec_s)]], colWidths=[W])
    auth_hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("PADDING",    (0, 0), (-1, -1), 7),
    ]))
    elems.append(auth_hdr)
    elems.append(Spacer(1, 8))

    issued_name   = (r.get("issued_name") or "___________________").strip()
    received_name = (r.get("received_name") or "___________________").strip()

    issued_sig   = _sig_image(sig_issued_bytes,   max_w=3 * cm, max_h=2 * cm) or Spacer(1, 32)
    received_sig = _sig_image(sig_received_bytes, max_w=3 * cm, max_h=2 * cm) or Spacer(1, 32)

    auth_tbl = Table([
        [Paragraph("<b>ISSUED BY</b>",   auth_s), Paragraph("<b>RECEIVED BY</b>", auth_s)],
        [Paragraph(f"Name: {issued_name}",   sig_lbl), Paragraph(f"Name: {received_name}", sig_lbl)],
        [issued_sig,                          received_sig],
        [Paragraph(f"Date: {rdate}",     sig_lbl), Paragraph("Date: ___________________",  sig_lbl)],
    ], colWidths=[W * 0.5, W * 0.5])
    auth_tbl.setStyle(TableStyle([
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ("PADDING",   (0, 0), (-1, -1), 8),
        ("LINEAFTER", (0, 0), (0, -1),  0.5, GREY_LINE),
    ]))
    elems.append(auth_tbl)
    elems.append(Spacer(1, 12))

    # 7. Logo
    logo = _logo_image()
    if logo:
        elems.append(logo)
    elems.append(Spacer(1, 6))

    # 8. Footer
    elems.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceBefore=4, spaceAfter=4))
    elems.append(Paragraph(
        "www.rincoltech.com  |  rincoltech@gmail.com  |  Tel: +256 775 102 684",
        foot_s,
    ))

    doc.build(elems)
    return buf.getvalue()
