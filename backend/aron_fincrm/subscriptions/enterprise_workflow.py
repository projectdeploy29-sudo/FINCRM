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
        customer_subject = 'Thank you for your Auron FIN CRM Enterprise inquiry'
        customer_body = (
            f'Hello {inquiry.full_name},\n\n'
            f'Thank you for contacting Auron FIN CRM about an Enterprise plan for {inquiry.organization_name}. '
            'We have received your inquiry and our team will review your requirements and contact you to discuss the next steps.\n\n'
            'There is nothing else you need to do right now. We will follow up using the contact details you provided.\n\n'
            'Kind regards,\nAuron FIN CRM Enterprise Team · Alpha Auron'
        )
        customer_html = (
            '<div style="margin:0;background:#f4f6fa;padding:32px 16px;font-family:Arial,sans-serif;color:#202940">'
            '<div style="max-width:600px;margin:0 auto;border:1px solid #e3e7ef;border-radius:12px;background:#fff;overflow:hidden">'
            '<div style="padding:20px 26px;background:#171d35;color:#fff;font-size:20px;font-weight:700">AURON FIN CRM</div>'
            '<div style="padding:28px 26px">'
            '<p style="margin:0 0 8px;color:#ec303b;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase">Enterprise inquiry</p>'
            '<h1 style="margin:0 0 16px;font-size:23px;color:#171d35">Thank you for getting in touch</h1>'
            f'<p style="margin:0 0 14px;line-height:1.6">Hello {escape(inquiry.full_name)},</p>'
            f'<p style="margin:0 0 14px;line-height:1.6">We have received your inquiry about an Enterprise plan for <strong>{escape(inquiry.organization_name)}</strong>.</p>'
            '<p style="margin:0 0 14px;line-height:1.6">Our team will review your requirements and contact you to discuss the next steps.</p>'
            '<p style="margin:0;line-height:1.6;color:#68758b">There is nothing else you need to do right now. We will follow up using the contact details you provided.</p>'
            '<p style="margin:24px 0 0;line-height:1.6">Kind regards,<br><strong>Auron FIN CRM Enterprise Team · Alpha Auron</strong></p>'
            '</div></div></div>'
        )
        inquiry.customer_email_sent = _send_message(
            customer_subject,
            customer_body,
            inquiry.email,
            html_message=customer_html,
        )

    if not only_unsent or not inquiry.admin_email_sent:
        admin_email = settings.ENTERPRISE_INQUIRY_ADMIN_EMAIL
        details = [
            ('Contact name', inquiry.full_name),
            ('Email address', inquiry.email),
            ('Phone number', inquiry.phone),
            ('Organization', inquiry.organization_name),
            ('Website', inquiry.website),
            ('LinkedIn profile', inquiry.linkedin_url),
            ('Requirements', inquiry.note),
        ]
        admin_body = '\n'.join([
            'A new request for an Auron FIN CRM Enterprise plan has been submitted.',
            'Please review the details below and follow up with the contact.',
            '',
            *[f'{label}: {value or "—"}' for label, value in details],
            '',
            'This inquiry is available in the Auron FIN CRM Enterprise management workspace.',
        ])
        admin_html = (
            '<div style="margin:0;background:#f4f6fa;padding:32px 16px;font-family:Arial,sans-serif;color:#202940">'
            '<div style="max-width:650px;margin:0 auto;border:1px solid #e3e7ef;border-radius:12px;background:#fff;overflow:hidden">'
            '<div style="padding:20px 26px;background:#171d35;color:#fff;font-size:20px;font-weight:700">AURON FIN CRM <span style="color:#ff858d;font-size:12px;font-weight:600">Enterprise</span></div>'
            '<div style="padding:26px">'
            '<p style="margin:0 0 8px;color:#ec303b;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase">New inquiry</p>'
            '<h1 style="margin:0 0 12px;font-size:22px;color:#171d35">Enterprise plan request</h1>'
            '<p style="margin:0 0 18px;line-height:1.6;color:#68758b">A prospective customer submitted a request. Review the information and follow up with the contact.</p>'
            '<table role="presentation" style="width:100%;border-collapse:collapse">'
            + ''.join(
                '<tr>'
                f'<th scope="row" style="width:160px;padding:10px 12px;border:1px solid #e8ebf1;background:#f8f9fb;text-align:left;vertical-align:top;font-size:12px;color:#5d6a80">{escape(label)}</th>'
                f'<td style="padding:10px 12px;border:1px solid #e8ebf1;vertical-align:top;font-size:13px;line-height:1.5;overflow-wrap:anywhere">{escape(value or "—")}</td>'
                '</tr>'
                for label, value in details
            )
            + '</table>'
            + '<p style="margin:18px 0 0;line-height:1.6;color:#68758b">This inquiry is available in the Auron FIN CRM Enterprise management workspace.</p>'
            + '</div></div></div>'
        )
        inquiry.admin_email_sent = _send_message(
            'New Auron FIN CRM Enterprise plan inquiry', admin_body, admin_email,
            html_message=admin_html,
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
            'Auron FIN CRM has prepared the Enterprise payment checkout following your discussion with our team.\n\n'
            f'Agreed amount: INR {checkout.amount} per {checkout.get_billing_cycle_display().lower()}\n\n'
            'Use this secure link within 48 hours to complete payment. After payment is verified, '
            'we will send a one-time organization registration link.\n'
            f'{_checkout_email(checkout, raw_token)}\n'
        )
        if not _send_message('Your Auron FIN CRM Enterprise payment checkout', body, inquiry.email):
            raise EnterpriseWorkflowError('The Razorpay order is ready, but the payment email could not be sent. Retry this admin action to send a fresh link.')

        inquiry.payment_link_email_sent_at = timezone.now()
        inquiry.status = EnterpriseInquiry.Status.PAYMENT_INITIATED
        inquiry.save(update_fields=['payment_link_email_sent_at', 'status'])
        return checkout
    except EnterpriseInquiry.DoesNotExist as error:
        raise EnterpriseWorkflowError('Enterprise inquiry was not found.') from error
