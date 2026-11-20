from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from finance.serializers import RepaymentPaymentSerializer
from organizations.dates import organization_local_date
from organizations.models import Organization
from rest_framework.exceptions import ValidationError


class PaymentDateValidationTests(TestCase):
    def test_historical_payment_is_allowed_and_future_payment_is_rejected(self):
        User = get_user_model()
        organization = Organization.objects.create(name='Payment dates', slug='payment-dates')
        user = User.objects.create_user(
            username='payment_date_user', password='test-password',
            default_organization=organization,
        )
        request = SimpleNamespace(user=user, headers={})
        serializer = RepaymentPaymentSerializer(context={'request': request})
        local_today = organization_local_date(request)
        historical = local_today - timedelta(days=1)

        self.assertEqual(serializer.validate_payment_date(historical), historical)
        with self.assertRaises(ValidationError):
            serializer.validate_payment_date(local_today + timedelta(days=1))
