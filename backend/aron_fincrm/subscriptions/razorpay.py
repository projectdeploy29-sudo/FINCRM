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
