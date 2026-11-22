import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.html import escape


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
        'Payment Successful – Complete Your FinCRM Enterprise Registration'
        if enterprise else 'Complete your FINCRM organization registration'
    )
    customer_name = checkout.customer_name or (checkout.enterprise_inquiry.full_name if enterprise else '')
    organization_name = (
        checkout.organization.name if checkout.organization_id else checkout.enterprise_inquiry.organization_name
    ) if enterprise else ''
    body = (
        'Your FINCRM payment has been confirmed.\n\n'
        + (f'Customer: {customer_name}\nOrganization: {organization_name}\n' if enterprise else '')
        + f'Plan: {checkout.plan.name}\n'
        + f'Billing: {cycle}\n'
        + f'Amount paid: {checkout.currency} {checkout.amount}\n\n'
        + f'Use this one-time registration link within {int(lifetime.total_seconds() // 3600)} hours to create your organization and admin account:\n'
        + f'{registration_url}\n\n'
        + 'This link is tied to the email address used for payment and cannot be used a second time.'
    )
    try:
        sent = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [checkout.purchaser_email],
            fail_silently=False,
            html_message=(
                '<p>Your FINCRM payment has been confirmed.</p>'
                + (f'<p><strong>Customer:</strong> {escape(customer_name)}<br><strong>Organization:</strong> {escape(organization_name)}</p>' if enterprise else '')
                + f'<p><strong>Plan:</strong> {escape(checkout.plan.name)}<br>'
                f'<strong>Billing:</strong> {escape(cycle)}<br>'
                f'<strong>Amount:</strong> {escape(checkout.currency)} {escape(checkout.amount)}</p>'
                f'<p><a href="{escape(registration_url)}" style="display:inline-block;padding:12px 18px;background:#1764e8;color:#fff;text-decoration:none;border-radius:6px">Complete registration</a></p>'
                f'<p>This one-time link expires in {int(lifetime.total_seconds() // 3600)} hours.</p>'
            ),
        )
    except Exception as error:
        raise RegistrationEmailError('Registration email could not be delivered.') from error
    if sent != 1:
        raise RegistrationEmailError('Registration email was not accepted by the mail backend.')
    return timezone.now()


def send_registration_completed(checkout, organization_name):
    """Send a best-effort completion receipt after the registration transaction commits."""
    inquiry = checkout.enterprise_inquiry if checkout.enterprise_inquiry_id else None
    customer_name = checkout.customer_name or (inquiry.full_name if inquiry else '')
    subject = 'Your FinCRM Enterprise registration is complete'
    body = (
        f'Hello {customer_name},\n\n'
        f'Your organization {organization_name} is registered with the {checkout.plan.name} plan. '
        'You can now sign in to FinCRM.\n\nFINCRM'
    )
    try:
        sent = send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, [checkout.purchaser_email],
            fail_silently=False,
            html_message=(
                f'<p>Hello {escape(customer_name)},</p>'
                f'<p><strong>{escape(organization_name)}</strong> is registered with the '
                f'<strong>{escape(checkout.plan.name)}</strong> plan. You can now sign in to FinCRM.</p>'
            ),
        )
        if sent != 1:
            raise RuntimeError('The mail backend did not accept the registration completion email.')
    except Exception:
        logger.exception('Registration completion email could not be delivered for checkout %s', checkout.pk)
