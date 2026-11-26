import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.utils import timezone
from django.utils.html import escape
from subscriptions.payment_documents import build_payment_receipt, build_test_gst_invoice


REGISTRATION_LINK_LIFETIME = timedelta(hours=48)
logger = logging.getLogger(__name__)


class RegistrationEmailError(Exception):
    pass


def hash_registration_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_registration_token():
    return secrets.token_urlsafe(32)


def send_registration_link(checkout, token, *, lifetime=REGISTRATION_LINK_LIFETIME):
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        raise RegistrationEmailError('SMTP email credentials are not configured.')
    registration_url = settings.FRONTEND_URL + '/?' + urlencode({'registration_token': token})
    cycle = checkout.get_billing_cycle_display().lower()
    enterprise = bool(checkout.enterprise_inquiry_id)
    subject = (
        'Payment confirmed - complete your Auron FIN CRM Enterprise registration'
        if enterprise else 'Complete your Auron FIN CRM organization registration'
    )
    customer_name = checkout.customer_name or (checkout.enterprise_inquiry.full_name if enterprise else '')
    organization_name = (
        checkout.organization.name if checkout.organization_id else checkout.enterprise_inquiry.organization_name
    ) if enterprise else ''
    lifetime_hours = int(lifetime.total_seconds() // 3600)
    body = (
        f'Hello {customer_name or "there"},\n\n'
        'Your Auron FIN CRM payment has been confirmed. Complete your organization registration using the secure link below.\n\n'
        + (f'Organization: {organization_name}\n' if enterprise else '')
        + f'Plan: {checkout.plan.name}\n'
        + f'Billing cycle: {cycle}\n'
        + f'Amount paid: {checkout.currency} {checkout.amount}\n'
        + f'Payment email: {checkout.purchaser_email}\n\n'
        + 'Attached: payment receipt and a GST invoice test draft. The GST draft contains NA placeholders and is not a valid tax invoice.\n\n'
        + f'Complete registration within {lifetime_hours} hours:\n{registration_url}\n\n'
        + f'For your security, this one-time link is tied to the payment email above, expires after {lifetime_hours} hours, and must not be forwarded. '
        + 'If you were not expecting this message or need help, contact Auron FIN CRM Support.\n\n'
        + 'Kind regards,\nAuron FIN CRM Support · Alpha Auron'
    )
    try:
        message = EmailMultiAlternatives(
            subject, body, settings.DEFAULT_FROM_EMAIL, [checkout.purchaser_email],
        )
        message.attach_alternative(
                '<div style="margin:0;background:#f4f6fa;padding:32px 16px;font-family:Arial,sans-serif;color:#202940">'
                '<div style="max-width:600px;margin:0 auto;border:1px solid #e3e7ef;border-radius:12px;background:#fff;overflow:hidden">'
                '<div style="padding:20px 26px;background:#171d35;color:#fff;font-size:20px;font-weight:700">AURON FIN CRM</div>'
                '<div style="padding:28px 26px">'
                '<p style="margin:0 0 8px;color:#16845a;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase">Payment confirmed</p>'
                '<h1 style="margin:0 0 16px;font-size:23px;color:#171d35">Complete your registration</h1>'
                f'<p style="margin:0 0 16px;line-height:1.6">Hello {escape(customer_name or "there")},</p>'
                '<p style="margin:0 0 16px;line-height:1.6">Your payment has been confirmed. Use the secure link below to create your organization and administrator account.</p>'
                + (f'<p style="margin:0 0 6px;line-height:1.5"><strong>Organization:</strong> {escape(organization_name)}</p>' if enterprise else '')
                + f'<p style="margin:0 0 6px;line-height:1.5"><strong>Plan:</strong> {escape(checkout.plan.name)}</p>'
                + f'<p style="margin:0 0 6px;line-height:1.5"><strong>Billing cycle:</strong> {escape(cycle)}</p>'
                + f'<p style="margin:0 0 6px;line-height:1.5"><strong>Amount paid:</strong> {escape(checkout.currency)} {escape(checkout.amount)}</p>'
                + f'<p style="margin:0 0 18px;line-height:1.5"><strong>Payment email:</strong> {escape(checkout.purchaser_email)}</p>'
                + '<p style="margin:0 0 18px;line-height:1.6;color:#68758b">Attached are your payment receipt and a GST invoice test draft. The draft is marked with NA placeholders and is not a valid tax invoice.</p>'
                + f'<p style="margin:22px 0"><a href="{escape(registration_url)}" style="display:inline-block;padding:12px 18px;border-radius:8px;background:#ec303b;color:#fff;text-decoration:none;font-weight:700">Complete registration</a></p>'
                + f'<p style="margin:0 0 12px;line-height:1.6;color:#68758b">This one-time link is tied to the payment email above, expires in {lifetime_hours} hours, and must not be forwarded.</p>'
                + '<p style="margin:0;line-height:1.6;color:#68758b">If you were not expecting this message or need help, contact Auron FIN CRM Support.</p>'
                + '<p style="margin:24px 0 0;line-height:1.6">Kind regards,<br><strong>Auron FIN CRM Support · Alpha Auron</strong></p>'
                + '</div></div></div>'
            , 'text/html'
        )
        receipt_reference, receipt_pdf = build_payment_receipt(checkout=checkout)
        invoice_reference, invoice_pdf = build_test_gst_invoice(checkout=checkout)
        message.attach(f'auron-fin-crm-payment-receipt-{receipt_reference}.pdf', receipt_pdf, 'application/pdf')
        message.attach(f'auron-fin-crm-gst-test-draft-{invoice_reference}.pdf', invoice_pdf, 'application/pdf')
        sent = message.send(fail_silently=False)
    except Exception as error:
        raise RegistrationEmailError('Registration email could not be delivered.') from error
    if sent != 1:
        raise RegistrationEmailError('Registration email was not accepted by the mail backend.')
    return timezone.now()


def send_registration_completed(checkout, organization_name):
    """Send a best-effort completion receipt after the registration transaction commits."""
    inquiry = checkout.enterprise_inquiry if checkout.enterprise_inquiry_id else None
    customer_name = checkout.customer_name or (inquiry.full_name if inquiry else '')
    subject = 'Your Auron FIN CRM Enterprise registration is complete'
    body = (
        f'Hello {customer_name},\n\n'
        f'Your organization {organization_name} is registered with the {checkout.plan.name} plan. '
        'You can now sign in to Auron FIN CRM.\n\nAuron FIN CRM'
    )
    try:
        sent = send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, [checkout.purchaser_email],
            fail_silently=False,
            html_message=(
                f'<p>Hello {escape(customer_name)},</p>'
                f'<p><strong>{escape(organization_name)}</strong> is registered with the '
                f'<strong>{escape(checkout.plan.name)}</strong> plan. You can now sign in to Auron FIN CRM.</p>'
            ),
        )
        if sent != 1:
            raise RuntimeError('The mail backend did not accept the registration completion email.')
    except Exception:
        logger.exception('Registration completion email could not be delivered for checkout %s', checkout.pk)
