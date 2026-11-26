"""Branded PDFs for verified Auron FIN CRM subscription payments."""

from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas


PAGE_WIDTH, PAGE_HEIGHT = A4
INK = colors.HexColor('#171D35')
INK_SOFT = colors.HexColor('#29344F')
RED = colors.HexColor('#EF303B')
RED_PALE = colors.HexColor('#FFF0F1')
MUTED = colors.HexColor('#77839A')
LINE = colors.HexColor('#E2E7F0')
SURFACE = colors.HexColor('#F4F6FA')
GREEN = colors.HexColor('#198B67')
GREEN_PALE = colors.HexColor('#EAF7F1')
WHITE = colors.white
ASSET_DIR = Path(__file__).with_name('assets')
LOGO_PATH = ASSET_DIR / 'auron_fin_crm_logo.png'
SEAL_PATH = ASSET_DIR / 'alpha_auron_seal.png'


def _money(currency, amount):
    return f'{currency} {Decimal(amount):,.2f}'


def _payment_values(checkout=None, payment=None):
    if payment is not None:
        checkout = payment.checkout
        paid_at = payment.paid_at or payment.created_at
        amount = payment.amount
        currency = payment.currency
        payment_id = payment.provider_payment_id or 'NA'
        order_id = checkout.razorpay_order_id if checkout else 'NA'
        plan_name = checkout.plan.name if checkout else (
            payment.subscription.plan.name if payment.subscription_id else 'Subscription payment'
        )
        cycle = checkout.get_billing_cycle_display() if checkout else (
            payment.subscription.get_billing_cycle_display() if payment.subscription_id else 'NA'
        )
        customer_email = checkout.purchaser_email if checkout else 'NA'
        customer_name = (checkout.customer_name or customer_email) if checkout else customer_email
        organization = (
            payment.subscription.organization.name if payment.subscription_id
            else checkout.organization.name if checkout and checkout.organization_id
            else 'NA'
        )
        reference_id = checkout.pk if checkout is not None else payment.pk
        customer_gstin = payment.invoice_customer_gstin
    else:
        paid_at = checkout.paid_at or timezone.now()
        amount = checkout.amount
        currency = checkout.currency
        payment_id = checkout.razorpay_payment_id or 'NA'
        order_id = checkout.razorpay_order_id or 'NA'
        plan_name = checkout.plan.name
        cycle = checkout.get_billing_cycle_display()
        customer_email = checkout.purchaser_email
        customer_name = checkout.customer_name or customer_email
        organization = checkout.organization.name if checkout.organization_id else (
            checkout.enterprise_inquiry.organization_name if checkout.enterprise_inquiry_id else 'Pending registration'
        )
        reference_id = checkout.pk
        customer_gstin = ''

    paid_at = timezone.localtime(paid_at) if timezone.is_aware(paid_at) else paid_at
    return {
        'receipt_reference': f'RCT-{str(reference_id).replace("-", "")[:16].upper()}',
        'customer_name': customer_name or 'NA',
        'customer_email': customer_email or 'NA',
        'organization': organization or 'NA',
        'plan_name': plan_name or 'NA',
        'billing_cycle': cycle or 'NA',
        'amount': amount,
        'currency': currency or 'INR',
        'paid_at': paid_at.strftime('%d %b %Y · %I:%M %p %Z'),
        'payment_id': payment_id,
        'order_id': order_id,
        'customer_gstin': customer_gstin,
    }


def _issuer_invoice_settings():
    from subscriptions.models import SubscriptionPlatformSettings

    settings_row = SubscriptionPlatformSettings.objects.filter(pk=1).first()
    if not settings_row:
        return {}
    return {
        'name': settings_row.invoice_issuer_name,
        'address': settings_row.invoice_issuer_address,
        'gstin': settings_row.invoice_issuer_gstin,
        'sac_hsn': settings_row.invoice_sac_hsn_code,
        'gst_rate': settings_row.invoice_gst_rate_percent,
    }


def _paragraph(c, value, x, top, width, *, size=9, leading=None, color=INK_SOFT,
               bold=False, alignment=TA_LEFT, max_height=100):
    font = 'Helvetica-Bold' if bold else 'Helvetica'
    style = ParagraphStyle(
        name='payment-document', fontName=font, fontSize=size,
        leading=leading or size * 1.35, textColor=color, alignment=alignment,
        spaceAfter=0, spaceBefore=0, wordWrap='CJK',
    )
    text = escape(str(value if value is not None else '')) or 'NA'
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, max_height)
    paragraph.drawOn(c, x, top - height)
    return height


def _rounded_card(c, x, y, width, height, *, fill=WHITE, stroke=LINE, radius=12):
    c.setLineWidth(0.8)
    c.setStrokeColor(stroke)
    c.setFillColor(fill)
    c.roundRect(x, y, width, height, radius, fill=1, stroke=1)


def _draw_header(c, title, reference, *, badge='PAID', badge_color=GREEN, subtitle='AURON FIN CRM · ALPHA AURON'):
    c.setFillColor(INK)
    c.rect(0, PAGE_HEIGHT - 132, PAGE_WIDTH, 132, fill=1, stroke=0)
    c.setFillColor(RED)
    c.rect(0, PAGE_HEIGHT - 132, 7, 132, fill=1, stroke=0)
    c.drawImage(ImageReader(str(LOGO_PATH)), 38, PAGE_HEIGHT - 78, width=46, height=46,
                preserveAspectRatio=True, anchor='c', mask='auto')
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(96, PAGE_HEIGHT - 49, 'AURON FIN CRM')
    c.setFillColor(colors.HexColor('#B9C4D8'))
    c.setFont('Helvetica', 8)
    c.drawString(97, PAGE_HEIGHT - 65, subtitle)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 17)
    c.drawString(40, PAGE_HEIGHT - 101, title)
    c.setFillColor(colors.HexColor('#CDD4E2'))
    c.setFont('Helvetica', 8.5)
    c.drawString(40, PAGE_HEIGHT - 117, f'Document reference  ·  {reference}')

    badge_text = badge.upper()
    badge_width = max(54, c.stringWidth(badge_text, 'Helvetica-Bold', 8) + 20)
    badge_x = PAGE_WIDTH - 40 - badge_width
    badge_y = PAGE_HEIGHT - 56
    c.setFillColor(colors.Color(badge_color.red, badge_color.green, badge_color.blue, alpha=0.18))
    c.roundRect(badge_x, badge_y - 8, badge_width, 25, 12.5, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(badge_x + badge_width / 2, badge_y + 1, badge_text)


def _draw_label_value(c, label, value, x, top, width, *, value_size=9.2, value_bold=True):
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 7)
    c.drawString(x, top - 10, label.upper())
    _paragraph(c, value, x, top - 17, width, size=value_size, leading=11.5,
               color=INK, bold=value_bold, max_height=28)


def _draw_cell(c, x, top, width, height, label, value):
    _rounded_card(c, x, top - height, width, height, fill=WHITE, stroke=LINE, radius=9)
    _draw_label_value(c, label, value, x + 12, top - 5, width - 24)


def _draw_seal(c, *, x, y, size=100):
    c.drawImage(ImageReader(str(SEAL_PATH)), x, y, width=size, height=size,
                preserveAspectRatio=True, anchor='c', mask='auto')


def _new_document(title, reference, *, badge='PAID', badge_color=GREEN):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    c.setTitle(f'{title} - {reference}')
    c.setAuthor('Auron FIN CRM · Alpha Auron')
    c.setSubject('Subscription payment document')
    c.setFillColor(SURFACE)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.roundRect(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40, 16, fill=1, stroke=0)
    _draw_header(c, title, reference, badge=badge, badge_color=badge_color)
    return c, buffer


def build_payment_receipt(checkout=None, payment=None):
    data = _payment_values(checkout=checkout, payment=payment)
    c, buffer = _new_document('PAYMENT RECEIPT', data['receipt_reference'])

    _rounded_card(c, 40, 590, PAGE_WIDTH - 80, 94, fill=colors.HexColor('#F8FAFD'))
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 7.5)
    c.drawString(58, 662, 'AMOUNT RECEIVED')
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 25)
    c.drawString(57, 627, _money(data['currency'], data['amount']))
    c.setFillColor(GREEN)
    c.setFont('Helvetica-Bold', 8)
    c.drawRightString(PAGE_WIDTH - 58, 631, 'PAYMENT CONFIRMED')
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 8)
    c.drawRightString(PAGE_WIDTH - 58, 613, data['paid_at'])

    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(40, 567, 'CUSTOMER & PLAN DETAILS')
    left = 40
    right = PAGE_WIDTH / 2 + 5
    cell_width = (PAGE_WIDTH - 90) / 2
    details = [
        ('Customer', data['customer_name']), ('Organization', data['organization']),
        ('Payment email', data['customer_email']), ('Plan', data['plan_name']),
        ('Billing cycle', data['billing_cycle']), ('Payment date', data['paid_at']),
    ]
    for row in range(3):
        top = 550 - row * 56
        _draw_cell(c, left, top, cell_width, 46, *details[row * 2])
        _draw_cell(c, right, top, cell_width, 46, *details[row * 2 + 1])

    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(40, 366, 'RAZORPAY PAYMENT REFERENCES')
    _rounded_card(c, 40, 270, PAGE_WIDTH - 80, 80, fill=colors.HexColor('#F8FAFD'))
    _draw_label_value(c, 'Payment ID', data['payment_id'], 56, 334, PAGE_WIDTH / 2 - 74, value_size=8.2)
    _draw_label_value(c, 'Order ID', data['order_id'], PAGE_WIDTH / 2 + 16, 334, PAGE_WIDTH / 2 - 76, value_size=8.2)
    c.setFillColor(GREEN_PALE)
    c.circle(61, 289, 5, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.setFont('Helvetica-Bold', 7.5)
    c.drawString(72, 286.5, 'Verified payment recorded by Auron FIN CRM')

    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(40, 230, 'THANK YOU FOR YOUR PAYMENT')
    _paragraph(c, 'Keep this receipt with your subscription records. It confirms payment status and is not a GST tax invoice.',
               40, 214, 350, size=8.5, leading=12, color=MUTED)
    _draw_seal(c, x=430, y=91, size=105)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(40, 79, PAGE_WIDTH - 40, 79)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7)
    c.drawString(40, 62, 'Auron FIN CRM  ·  Powered by Alpha Auron')
    c.drawRightString(PAGE_WIDTH - 40, 62, 'Payment receipt')

    c.showPage()
    c.save()
    return data['receipt_reference'], buffer.getvalue()


def build_test_gst_invoice(checkout=None, payment=None):
    data = _payment_values(checkout=checkout, payment=payment)
    issuer = _issuer_invoice_settings()
    gst_rate = issuer.get('gst_rate')
    taxable_value = None
    gst_amount = None
    if gst_rate is not None:
        gross_amount = Decimal(data['amount'])
        divisor = Decimal('1') + Decimal(gst_rate) / Decimal('100')
        taxable_value = (gross_amount / divisor).quantize(Decimal('0.01'))
        gst_amount = gross_amount - taxable_value
    invoice_reference = f"GST-TEST-{data['receipt_reference'].removeprefix('RCT-')}"
    c, buffer = _new_document(
        'GST TAX INVOICE · TEST DRAFT', invoice_reference,
        badge='TEST DRAFT', badge_color=RED,
    )

    c.setFillColor(RED_PALE)
    c.roundRect(40, 657, PAGE_WIDTH - 80, 34, 8, fill=1, stroke=0)
    c.setFillColor(RED)
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(PAGE_WIDTH / 2, 671, 'TEST DOCUMENT  ·  NOT A VALID GST TAX INVOICE')

    _rounded_card(c, 40, 583, PAGE_WIDTH - 80, 58, fill=colors.HexColor('#F8FAFD'))
    _draw_label_value(c, 'Invoice reference', invoice_reference, 56, 630, 230)
    _draw_label_value(c, 'Issue / payment date', data['paid_at'], PAGE_WIDTH / 2 + 8, 630, 220)

    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 8.5)
    c.drawString(40, 563, 'SUPPLIER')
    c.drawString(PAGE_WIDTH / 2 + 5, 563, 'BILLED TO')
    card_width = (PAGE_WIDTH - 90) / 2
    _rounded_card(c, 40, 461, card_width, 91)
    _rounded_card(c, PAGE_WIDTH / 2 + 5, 461, card_width, 91)
    _draw_label_value(c, 'Legal name', issuer.get('name') or 'NA - testing placeholder', 53, 544, card_width - 24, value_size=8.4)
    _draw_label_value(c, 'Address', issuer.get('address') or 'NA - testing placeholder', 53, 518, card_width - 24, value_size=8.4)
    _draw_label_value(c, 'GSTIN', issuer.get('gstin') or 'NA - testing placeholder', 53, 492, card_width - 24, value_size=8.4)
    bill_x = PAGE_WIDTH / 2 + 18
    _draw_label_value(c, 'Organization', data['organization'], bill_x, 544, card_width - 26, value_size=8.4)
    _draw_label_value(c, 'Customer / email', f"{data['customer_name']} · {data['customer_email']}", bill_x, 518, card_width - 26, value_size=8.1)
    _draw_label_value(c, 'Customer GSTIN', data.get('customer_gstin') or 'NA - testing placeholder', bill_x, 492, card_width - 26, value_size=8.4)

    table_x = 40
    table_width = PAGE_WIDTH - 80
    table_top = 452
    header_height = 28
    row_height = 58
    c.setFillColor(INK)
    c.roundRect(table_x, table_top - header_height, table_width, header_height, 7, fill=1, stroke=0)
    headings = [('DESCRIPTION', 54), ('SAC / HSN', 285), ('TAXABLE VALUE', 342), ('GST', 425), ('TOTAL', 485)]
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 6.8)
    for label, x in headings:
        c.drawString(x, table_top - 18, label)
    row_y = table_top - header_height - row_height
    c.setFillColor(WHITE)
    c.setStrokeColor(LINE)
    c.roundRect(table_x, row_y, table_width, row_height, 7, fill=1, stroke=1)
    _paragraph(c, f"Auron FIN CRM subscription - {data['plan_name']} ({data['billing_cycle']})",
               54, table_top - header_height - 10, 230, size=8, leading=10.5, bold=True)
    _paragraph(c, issuer.get('sac_hsn') or 'NA', 285, table_top - header_height - 10, 45, size=8.2, color=INK)
    _paragraph(c, _money(data['currency'], taxable_value) if taxable_value is not None else 'NA',
               342, table_top - header_height - 10, 70, size=7.2, color=INK)
    _paragraph(c, _money(data['currency'], gst_amount) if gst_amount is not None else 'NA',
               425, table_top - header_height - 10, 45, size=7.0, color=INK)
    _paragraph(c, _money(data['currency'], data['amount']), 485, table_top - header_height - 10, 60,
               size=7.5, bold=True, alignment=TA_RIGHT)

    summary_top = row_y - 16
    _rounded_card(c, 40, summary_top - 67, PAGE_WIDTH - 80, 67, fill=colors.HexColor('#F8FAFD'))
    _draw_label_value(c, 'Taxable value', _money(data['currency'], taxable_value) if taxable_value is not None else 'NA - testing placeholder', 56, summary_top - 10, 220, value_size=8.6)
    gst_summary = f'{gst_rate}% · {_money(data["currency"], gst_amount)}' if gst_amount is not None else 'NA - tax calculation not configured'
    _draw_label_value(c, 'GST rate / amount', gst_summary, 56, summary_top - 39, 250, value_size=8.6)
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 7)
    c.drawRightString(PAGE_WIDTH - 56, summary_top - 21, 'TOTAL PAID')
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 14)
    c.drawRightString(PAGE_WIDTH - 56, summary_top - 48, _money(data['currency'], data['amount']))

    ref_y = summary_top - 89
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 7)
    c.drawString(42, ref_y, f"RAZORPAY PAYMENT ID  ·  {data['payment_id']}")
    c.drawString(42, ref_y - 15, f"RAZORPAY ORDER ID  ·  {data['order_id']}")

    disclaimer = ('TESTING SAMPLE ONLY. This draft may display issuer and draft tax values entered in platform settings, but it is not a valid GST tax invoice '
                  'and must not be used to claim input tax credit.')
    _paragraph(c, disclaimer, 42, ref_y - 37, 355, size=7.4, leading=10.4, color=MUTED)
    _draw_seal(c, x=430, y=91, size=105)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(40, 79, PAGE_WIDTH - 40, 79)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7)
    c.drawString(40, 62, 'Auron FIN CRM  ·  Powered by Alpha Auron')
    c.drawRightString(PAGE_WIDTH - 40, 62, 'GST test draft')

    c.showPage()
    c.save()
    return invoice_reference, buffer.getvalue()
