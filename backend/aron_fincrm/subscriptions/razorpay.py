import hashlib
import hmac

from django.conf import settings


class RazorpayConfigurationError(Exception):
    pass


class RazorpayProviderError(Exception):
    pass


def _credentials():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_id or not key_secret:
        raise RazorpayConfigurationError('Razorpay credentials are not configured.')
    return key_id, key_secret


def _response_json(response):
    try:
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        raise RazorpayProviderError('Razorpay request failed.') from error
    if not isinstance(payload, dict):
        raise RazorpayProviderError('Razorpay returned an invalid response.')
    return payload


def create_order(checkout):
    import requests

    key_id, key_secret = _credentials()
    amount_subunits = int(checkout.amount * 100)
    try:
        response = requests.post(
            'https://api.razorpay.com/v1/orders',
            auth=(key_id, key_secret),
            json={
                'amount': amount_subunits,
                'currency': checkout.currency,
                'receipt': 'FIN-' + checkout.id.hex,
                'notes': {
                    'plan_code': checkout.plan.code,
                    'billing_cycle': checkout.billing_cycle,
                    'checkout_id': str(checkout.id),
                },
            },
            timeout=20,
        )
    except requests.RequestException as error:
        raise RazorpayProviderError('Could not create a Razorpay order.') from error
    payload = _response_json(response)
    if (
        not payload.get('id')
        or payload.get('amount') != amount_subunits
        or payload.get('currency') != checkout.currency
    ):
        raise RazorpayProviderError('Razorpay order details did not match the checkout.')
    return key_id, payload


def create_plan(plan, *, billing_cycle):
    """Create a Razorpay Plan using POST /v1/plans (amounts are currency subunits)."""
    import requests

    key_id, key_secret = _credentials()
    if billing_cycle not in {'MONTHLY', 'YEARLY'}:
        raise ValueError('Recurring billing must be monthly or yearly.')
    if not plan.subscription_total_count:
        raise ValueError('Recurring plan duration (total billing cycles) is required.')
    amount = plan.monthly_price if billing_cycle == 'MONTHLY' else plan.yearly_price
    if amount is None or amount <= 0:
        raise ValueError('A positive recurring amount is required.')
    payload = {
        'period': 'monthly' if billing_cycle == 'MONTHLY' else 'yearly',
        'interval': 1,
        'item': {
            'name': plan.name[:255],
            'amount': int(amount * 100),
            'currency': 'INR',
            'description': (plan.description or plan.name)[:255],
        },
        'notes': {'fincrm_plan_id': str(plan.pk), 'plan_code': plan.code},
    }
    try:
        response = requests.post(
            'https://api.razorpay.com/v1/plans',
            auth=(key_id, key_secret), json=payload, timeout=20,
        )
    except requests.RequestException as error:
        raise RazorpayProviderError('Could not create a Razorpay subscription plan.') from error
    result = _response_json(response)
    if not result.get('id'):
        raise RazorpayProviderError('Razorpay did not return a subscription plan ID.')
    return result


def create_subscription(checkout, *, total_count):
    """Create a Razorpay Subscription using POST /v1/subscriptions."""
    import requests

    key_id, key_secret = _credentials()
    if not checkout.plan.razorpay_plan_id:
        raise RazorpayConfigurationError('The custom plan has no Razorpay Plan ID.')
    if not isinstance(total_count, int) or total_count < 1:
        raise ValueError('Recurring duration must be a positive cycle count.')
    payload = {
        'plan_id': checkout.plan.razorpay_plan_id,
        'total_count': total_count,
        'quantity': 1,
        'customer_notify': False,
        'notes': {
            'fincrm_checkout_id': str(checkout.pk),
            'fincrm_inquiry_id': str(checkout.enterprise_inquiry_id or ''),
        },
    }
    try:
        response = requests.post(
            'https://api.razorpay.com/v1/subscriptions',
            auth=(key_id, key_secret), json=payload, timeout=20,
        )
    except requests.RequestException as error:
        raise RazorpayProviderError('Could not create a Razorpay subscription.') from error
    result = _response_json(response)
    if not result.get('id') or result.get('plan_id') != checkout.plan.razorpay_plan_id:
        raise RazorpayProviderError('Razorpay subscription details did not match the approved plan.')
    return key_id, result


def cancel_subscription(subscription_id, *, cancel_at_cycle_end=False):
    """Cancel a Razorpay Subscription through its documented cancel endpoint."""
    import requests

    key_id, key_secret = _credentials()
    try:
        response = requests.post(
            f'https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel',
            auth=(key_id, key_secret),
            json={'cancel_at_cycle_end': bool(cancel_at_cycle_end)},
            timeout=20,
        )
    except requests.RequestException as error:
        raise RazorpayProviderError('Could not cancel the Razorpay subscription.') from error
    result = _response_json(response)
    if result.get('id') != subscription_id:
        raise RazorpayProviderError('Razorpay returned a different subscription during cancellation.')
    return result


def fetch_payment(payment_id):
    import requests

    key_id, key_secret = _credentials()
    try:
        response = requests.get(
            'https://api.razorpay.com/v1/payments/' + payment_id,
            auth=(key_id, key_secret),
            timeout=20,
        )
    except requests.RequestException as error:
        raise RazorpayProviderError('Could not verify the Razorpay payment.') from error
    return _response_json(response)


def valid_checkout_signature(order_id, payment_id, signature):
    _, key_secret = _credentials()
    message = (order_id + '|' + payment_id).encode('utf-8')
    expected = hmac.new(key_secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def valid_webhook_signature(raw_body, signature):
    key_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not key_secret or not signature:
        return False
    expected = hmac.new(key_secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
