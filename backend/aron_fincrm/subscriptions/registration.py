import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


REGISTRATION_LINK_LIFETIME = timedelta(hours=48)


class RegistrationEmailError(Exception):
    pass


def hash_registration_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_registration_token():
    return secrets.token_urlsafe(32)


def send_registration_link(checkout, token):
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        raise RegistrationEmailError('SMTP email credentials are not configured.')
    registration_url = settings.FRONTEND_URL + '/?' + urlencode({'registration_token': token})
    cycle = checkout.get_billing_cycle_display().lower()
    subject = 'Complete your FINCRM organization registration'
    body = (
        'Your FINCRM payment has been confirmed.\n\n'
        f'Plan: {checkout.plan.name}\n'
        f'Billing: {cycle}\n'
        f'Amount paid: {checkout.currency} {checkout.amount}\n\n'
        'Use this one-time registration link within 48 hours to create your organization and admin account:\n'
        f'{registration_url}\n\n'
        'This link is tied to the email address used for payment and cannot be used a second time.'
    )
    try:
        sent = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [checkout.purchaser_email],
            fail_silently=False,
        )
    except Exception as error:
        raise RegistrationEmailError('Registration email could not be delivered.') from error
    if sent != 1:
        raise RegistrationEmailError('Registration email was not accepted by the mail backend.')
    return timezone.now()
