from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from subscriptions.models import EnterpriseInquiry, Plan, PlanCheckout, Subscription
from subscriptions.razorpay import (
    RazorpayConfigurationError,
    RazorpayProviderError,
    create_order,
)
from subscriptions.registration import create_registration_token, hash_registration_token


class EnterpriseWorkflowError(Exception):
    pass


ENTERPRISE_CHECKOUT_LIFETIME = timedelta(hours=48)


def _send_message(subject, body, recipient, *, html_message=None):
    if not recipient:
        return False
    try:
        return send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
            html_message=html_message,
        ) == 1
    except Exception:
        return False


def send_inquiry_notifications(inquiry, *, only_unsent=True):
    """Attempt each inquiry notification once; failed sends remain retryable by an admin."""
    if not only_unsent or not inquiry.customer_email_sent:
        inquiry.customer_email_sent = _send_message(
            'We received your FINCRM enterprise inquiry',
            (
                f'Hello {inquiry.full_name},\n\n'
                f'We received your enterprise inquiry for {inquiry.organization_name}. '
                'Our team will contact you soon.\n\nFINCRM'
            ),
            inquiry.email,
            html_message=(
                f'<p>Hello {escape(inquiry.full_name)},</p>'
                f'<p>We received your Enterprise inquiry for <strong>{escape(inquiry.organization_name)}</strong>. '
                'Our team will contact you soon.</p><p>FINCRM</p>'
            ),
        )

    if not only_unsent or not inquiry.admin_email_sent:
        admin_email = settings.ENTERPRISE_INQUIRY_ADMIN_EMAIL
        details = [
            'A new FINCRM Enterprise inquiry has arrived.',
            f'Name: {inquiry.full_name}',
            f'Email: {inquiry.email}',
            f'Phone: {inquiry.phone}',
            f'Organization: {inquiry.organization_name}',
            f'Website: {inquiry.website or "—"}',
            f'LinkedIn: {inquiry.linkedin_url or "—"}',
            f'Notes / requirements: {inquiry.note or "—"}',
        ]
        inquiry.admin_email_sent = _send_message(
            'FINCRM enterprise plan inquiry', '\n'.join(details), admin_email,
            html_message=(
                '<h2>A new FINCRM Enterprise inquiry has arrived</h2><dl>'
                + ''.join(
                    f'<dt><strong>{escape(label)}</strong></dt><dd>{escape(value or "—")}</dd>'
                    for label, value in (
                        ('Name', inquiry.full_name), ('Email', inquiry.email),
                        ('Phone', inquiry.phone), ('Organization', inquiry.organization_name),
                        ('Website', inquiry.website), ('LinkedIn', inquiry.linkedin_url),
                        ('Notes / requirements', inquiry.note),
                    )
                )
                + '</dl>'
            ),
        )

    inquiry.save(update_fields=['customer_email_sent', 'admin_email_sent'])
    return inquiry.customer_email_sent and inquiry.admin_email_sent


def _checkout_email(checkout, raw_token):
    query = urlencode({
        'enterprise_checkout': raw_token,
    })
    return f'{settings.FRONTEND_URL}/?{query}'


def initiate_enterprise_checkout(inquiry_id):
    """Create or reuse the negotiated Enterprise order, then email its short-lived access link."""
    try:
        with transaction.atomic():
            inquiry = EnterpriseInquiry.objects.select_for_update().get(pk=inquiry_id)
            if inquiry.status != EnterpriseInquiry.Status.AGREED:
                raise EnterpriseWorkflowError('Set the inquiry status to Agreement reached after review.')
            if not inquiry.agreed_amount or inquiry.agreed_amount <= 0:
                raise EnterpriseWorkflowError('Enter a positive agreed amount before creating checkout.')
            if inquiry.billing_cycle not in Subscription.BillingCycle.values:
                raise EnterpriseWorkflowError('Choose the agreed monthly or yearly billing cycle.')

            plan = Plan.objects.filter(code='enterprise', is_active=True).first()
            if not plan:
                raise EnterpriseWorkflowError('The active Enterprise plan is missing from the plan catalog.')

            checkout = PlanCheckout.objects.filter(enterprise_inquiry=inquiry).first()
            create_provider_order = False
            if checkout is None:
                checkout = PlanCheckout.objects.create(
                    plan=plan,
                    organization=inquiry.organization,
                    enterprise_inquiry=inquiry,
                    billing_cycle=inquiry.billing_cycle,
                    purchaser_email=inquiry.email,
                    amount=inquiry.agreed_amount,
                    currency='INR',
                    status=PlanCheckout.Status.CREATING,
                )
                create_provider_order = True
            elif checkout.status == PlanCheckout.Status.FAILED:
                checkout.plan = plan
                checkout.organization = inquiry.organization
                checkout.billing_cycle = inquiry.billing_cycle
                checkout.purchaser_email = inquiry.email
                checkout.amount = inquiry.agreed_amount
                checkout.status = PlanCheckout.Status.CREATING
                checkout.save(update_fields=[
                    'plan', 'organization', 'billing_cycle', 'purchaser_email', 'amount', 'status',
                ])
                create_provider_order = True
            elif checkout.status != PlanCheckout.Status.PENDING or not checkout.razorpay_order_id:
                raise EnterpriseWorkflowError('An Enterprise checkout for this inquiry is already being processed.')
            elif (
                checkout.amount != inquiry.agreed_amount
                or checkout.billing_cycle != inquiry.billing_cycle
                or checkout.purchaser_email.casefold() != inquiry.email.casefold()
                or checkout.organization_id != inquiry.organization_id
            ):
                raise EnterpriseWorkflowError('The quote changed after a payment order was created. Do not email its stale amount; close this inquiry and start a new approved checkout.')
            elif inquiry.payment_link_email_sent_at:
                raise EnterpriseWorkflowError('A payment link was already emailed. Clear its sent timestamp only to deliberately resend it.')

        if create_provider_order:
            try:
                _key_id, order = create_order(checkout)
            except (RazorpayConfigurationError, RazorpayProviderError, ImportError) as error:
                checkout.status = PlanCheckout.Status.FAILED
                checkout.save(update_fields=['status'])
                raise EnterpriseWorkflowError('Razorpay could not create the Enterprise order. Check provider configuration and retry.') from error
            checkout.razorpay_order_id = order['id']
            checkout.status = PlanCheckout.Status.PENDING
            checkout.save(update_fields=['razorpay_order_id', 'status'])

        raw_token = create_registration_token()
        checkout.enterprise_access_token_hash = hash_registration_token(raw_token)
        checkout.enterprise_access_token_expires_at = timezone.now() + ENTERPRISE_CHECKOUT_LIFETIME
        checkout.save(update_fields=[
            'enterprise_access_token_hash', 'enterprise_access_token_expires_at',
        ])

        body = (
            'FinCRM has prepared the Enterprise payment checkout following your discussion with our team.\n\n'
            f'Agreed amount: INR {checkout.amount} per {checkout.get_billing_cycle_display().lower()}\n\n'
            'Use this secure link within 48 hours to complete payment. After payment is verified, '
            'we will send a one-time organization registration link.\n'
            f'{_checkout_email(checkout, raw_token)}\n'
        )
        if not _send_message('Your FINCRM Enterprise payment checkout', body, inquiry.email):
            raise EnterpriseWorkflowError('The Razorpay order is ready, but the payment email could not be sent. Retry this admin action to send a fresh link.')

        inquiry.payment_link_email_sent_at = timezone.now()
        inquiry.status = EnterpriseInquiry.Status.PAYMENT_INITIATED
        inquiry.save(update_fields=['payment_link_email_sent_at', 'status'])
        return checkout
    except EnterpriseInquiry.DoesNotExist as error:
        raise EnterpriseWorkflowError('Enterprise inquiry was not found.') from error
