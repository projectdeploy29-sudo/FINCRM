from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from subscriptions.models import EnterpriseInquiry, Payment, PlanCheckout, RazorpayWebhookEvent, Subscription
from subscriptions.registration import create_registration_token, hash_registration_token, send_registration_link


class WebhookProcessingError(Exception):
    pass


def _entity(payload, key):
    return (payload.get('payload') or {}).get(key, {}).get('entity') or {}


def _checkout_for_order(order_id):
    return PlanCheckout.objects.select_for_update().filter(razorpay_order_id=order_id).first()


def _checkout_for_subscription(subscription_id):
    return PlanCheckout.objects.select_for_update().select_related('plan', 'enterprise_inquiry').filter(
        razorpay_subscription_id=subscription_id,
    ).first()


def _record_payment(checkout, entity, status_value):
    payment_id = entity.get('id')
    if not payment_id:
        return None
    payment, _ = Payment.objects.get_or_create(
        provider_payment_id=payment_id,
        defaults={
            'subscription_id': None,
            'checkout': checkout,
            'amount': Decimal(str(entity.get('amount', int(checkout.amount * 100)))) / Decimal('100'),
            'currency': entity.get('currency') or checkout.currency,
            'provider': 'RAZORPAY',
            'status': status_value,
            'paid_at': timezone.now() if status_value == Payment.Status.SUCCEEDED else None,
        },
    )
    if payment.checkout_id != checkout.pk:
        raise WebhookProcessingError('Payment ID is already associated with another checkout.')
    if payment.status != status_value and payment.status != Payment.Status.SUCCEEDED:
        payment.status = status_value
        if status_value == Payment.Status.SUCCEEDED:
            payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at'])
    return payment


def _send_registration_invitation(checkout):
    if checkout.registration_email_sent_at:
        return
    token = create_registration_token()
    checkout.registration_token_hash = hash_registration_token(token)
    checkout.registration_token_expires_at = timezone.now() + timedelta(hours=24)
    checkout.save(update_fields=['registration_token_hash', 'registration_token_expires_at'])
    sent_at = send_registration_link(checkout, token, lifetime=timedelta(hours=24))
    checkout.registration_email_sent_at = sent_at
    checkout.save(update_fields=['registration_email_sent_at'])


def process_razorpay_event(event_id, payload, payload_sha256):
    """Process a signed webhook once; an exception rolls back the inbox claim for provider retry."""
    event_type = payload.get('event', '')
    send_registration = None
    with transaction.atomic():
        try:
            with transaction.atomic():
                event = RazorpayWebhookEvent.objects.create(
                    event_id=event_id,
                    event_type=event_type,
                    payload_sha256=payload_sha256,
                )
        except IntegrityError:
            event = RazorpayWebhookEvent.objects.select_for_update().filter(event_id=event_id).first()
            if not event:
                raise WebhookProcessingError('The webhook event could not be claimed.')
            if event.payload_sha256 != payload_sha256:
                raise WebhookProcessingError('A webhook event ID was reused with a different payload.')
            if event.processed_at:
                return 'duplicate'
            event.event_type = event_type
            event.error = ''
            event.save(update_fields=['event_type', 'error'])

        if event_type == 'payment.captured':
            payment = _entity(payload, 'payment')
            order = _entity(payload, 'order')
            order_id = payment.get('order_id') or order.get('id')
            subscription_id = payment.get('subscription_id')
            checkout = _checkout_for_order(order_id) if order_id else (_checkout_for_subscription(subscription_id) if subscription_id else None)
            if checkout and checkout.enterprise_inquiry_id:
                if (not payment or payment.get('status') != 'captured'
                        or payment.get('currency') != checkout.currency
                        or payment.get('amount') != int(checkout.amount * 100)):
                    raise WebhookProcessingError('Captured payment does not match the approved order amount.')
                if checkout.payment_mode == 'recurring' and subscription_id != checkout.razorpay_subscription_id:
                    raise WebhookProcessingError('Captured payment does not match the approved subscription.')
                payment_record = _record_payment(checkout, payment, Payment.Status.SUCCEEDED)
                if subscription_id:
                    local_subscription = Subscription.objects.filter(razorpay_subscription_id=subscription_id).first()
                    if local_subscription and not payment_record.subscription_id:
                        payment_record.subscription = local_subscription
                        payment_record.invoice_reference = 'INV-' + local_subscription.Subscriptioncode
                        payment_record.save(update_fields=['subscription', 'invoice_reference'])
                        if not local_subscription.payment_id:
                            local_subscription.payment = payment_record
                            local_subscription.save(update_fields=['payment'])
                if order_id and checkout.status in {PlanCheckout.Status.PENDING, PlanCheckout.Status.PENDING_AUTHORIZATION, PlanCheckout.Status.PAID}:
                    checkout.razorpay_payment_id = payment['id']
                    checkout.paid_at = timezone.now()
                    checkout.status = PlanCheckout.Status.PAID
                    checkout.save(update_fields=['razorpay_payment_id', 'paid_at', 'status'])
                    if not checkout.registration_email_sent_at:
                        send_registration = checkout.pk

        elif event_type == 'payment.failed':
            payment = _entity(payload, 'payment')
            order_id = payment.get('order_id')
            subscription_id = payment.get('subscription_id')
            checkout = _checkout_for_order(order_id) if order_id else (_checkout_for_subscription(subscription_id) if subscription_id else None)
            if checkout and checkout.enterprise_inquiry_id and payment.get('currency') == checkout.currency:
                payment_record = _record_payment(checkout, payment, Payment.Status.FAILED)
                if subscription_id:
                    local_subscription = Subscription.objects.filter(razorpay_subscription_id=subscription_id).first()
                    if local_subscription and local_subscription.status == Subscription.Status.ACTIVE:
                        local_subscription.status = Subscription.Status.PAST_DUE
                        local_subscription.save(update_fields=['status'])

        elif event_type.startswith('subscription.'):
            subscription_entity = _entity(payload, 'subscription')
            provider_id = subscription_entity.get('id')
            checkout = _checkout_for_subscription(provider_id) if provider_id else None
            if checkout and checkout.enterprise_inquiry_id:
                provider_status = subscription_entity.get('status', '')
                local_subscription = Subscription.objects.filter(razorpay_subscription_id=provider_id).first()
                if event_type == 'subscription.activated':
                    if checkout.status in {PlanCheckout.Status.PENDING_AUTHORIZATION, PlanCheckout.Status.PENDING, PlanCheckout.Status.PAID}:
                        checkout.status = PlanCheckout.Status.PAID
                        checkout.paid_at = timezone.now()
                        checkout.save(update_fields=['status', 'paid_at'])
                        if not checkout.registration_email_sent_at:
                            send_registration = checkout.pk
                elif event_type == 'subscription.charged':
                    payment_entity = _entity(payload, 'payment')
                    payment = _record_payment(checkout, payment_entity, Payment.Status.SUCCEEDED)
                    if local_subscription and payment and not payment.subscription_id:
                        payment.subscription = local_subscription
                        payment.save(update_fields=['subscription'])
                        duration = timedelta(days=30 if checkout.billing_cycle == Subscription.BillingCycle.MONTHLY else 365)
                        local_subscription.next_billing_date = (timezone.now() + duration).date()
                        local_subscription.status = Subscription.Status.ACTIVE
                        local_subscription.save(update_fields=['end_date', 'next_billing_date', 'status'])
                elif event_type in {'subscription.halted', 'subscription.pending', 'subscription.paused'} and local_subscription:
                    local_subscription.status = Subscription.Status.HALTED if event_type in {'subscription.halted', 'subscription.paused'} else Subscription.Status.PAST_DUE
                    local_subscription.save(update_fields=['status'])
                    payment_entity = _entity(payload, 'payment')
                    if payment_entity:
                        _record_payment(checkout, payment_entity, Payment.Status.FAILED)
                elif event_type == 'subscription.cancelled' and local_subscription:
                    local_subscription.status = Subscription.Status.CANCELLED
                    local_subscription.cancelled_at = timezone.now()
                    local_subscription.save(update_fields=['status', 'cancelled_at'])
                elif event_type == 'subscription.completed' and local_subscription:
                    local_subscription.status = Subscription.Status.EXPIRED
                    local_subscription.save(update_fields=['status'])
                elif event_type == 'subscription.resumed' and local_subscription:
                    local_subscription.status = Subscription.Status.ACTIVE
                    local_subscription.save(update_fields=['status'])

        event.processed_at = timezone.now()
        event.save(update_fields=['processed_at'])

    if send_registration:
        checkout = PlanCheckout.objects.select_related('plan').get(pk=send_registration)
        try:
            _send_registration_invitation(checkout)
        except Exception as error:
            RazorpayWebhookEvent.objects.filter(event_id=event_id).update(
                processed_at=None,
                error='Registration invitation delivery failed.',
            )
            raise WebhookProcessingError('Registration invitation could not be delivered.') from error
    return 'processed'
