import uuid
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from organizations.models import Organization
from subscriptions.enterprise_workflow import initiate_enterprise_checkout
from subscriptions.entitlements import active_subscription, enforce_resource_limit
from subscriptions.models import EnterpriseInquiry, Plan, PlanCheckout, Payment, Subscription, RazorpayWebhookEvent
from subscriptions.registration import hash_registration_token, RegistrationEmailError
from subscriptions.serializers import PlanSerializer


class SubscriptionPricingTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name='Pricing test plan',
            code='pricing-test-plan',
            monthly_price='1234.00',
            yearly_price='12345.00',
            max_employees=20,
            max_leads=200,
            features={'lead_management': True},
        )
        self.plan.refresh_from_db()
        self.client = APIClient()

    def test_catalog_hides_unconfirmed_prices_and_disables_checkout(self):
        with override_settings(SUBSCRIPTION_CHECKOUT_ENABLED=False):
            response = self.client.get('/api/v1/subscriptions/plans/')

        self.assertEqual(response.status_code, 200, response.data)
        plan = next(row for row in response.data if row['code'] == self.plan.code)
        self.assertIsNone(plan['monthly_price'])
        self.assertIsNone(plan['yearly_price'])
        self.assertFalse(plan['checkout_enabled'])

    def test_checkout_is_closed_without_creating_an_order_or_checkout_row(self):
        with override_settings(SUBSCRIPTION_CHECKOUT_ENABLED=False):
            response = self.client.post(
                '/api/v1/subscriptions/checkout/create/',
                {'plan_id': str(self.plan.id), 'billing_cycle': 'MONTHLY', 'email': 'buyer@example.test'},
                format='json',
            )

        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(PlanCheckout.objects.count(), 0)

    @override_settings(SUBSCRIPTION_CHECKOUT_ENABLED=True)
    @patch('subscriptions.views.create_razorpay_order')
    def test_enabled_checkout_uses_database_price_and_creates_a_pending_order(self, create_order):
        self.plan.prices_confirmed = True
        self.plan.save(update_fields=['prices_confirmed'])
        create_order.return_value = ('rzp_test_key', {
            'id': 'order_unit_test',
            'amount': 123400,
            'currency': 'INR',
        })

        response = self.client.post(
            '/api/v1/subscriptions/checkout/create/',
            {'plan_id': str(self.plan.id), 'billing_cycle': 'MONTHLY', 'email': 'buyer@example.test'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['amount'], 123400)
        create_order.assert_called_once()
        checkout = PlanCheckout.objects.get(razorpay_order_id='order_unit_test')
        self.assertEqual(checkout.amount, self.plan.monthly_price)
        self.assertEqual(checkout.status, PlanCheckout.Status.PENDING)


class SubscriptionPaymentVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(name='Checkout Org', slug='checkout-org')
        self.admin = User.objects.create_user(
            username='checkout_admin',
            email='checkout_admin@example.test',
            password='test-password',
            default_organization=self.organization,
            is_staff=True,
        )
        self.plan = Plan.objects.create(
            name='Verification plan', code='verification-plan',
            monthly_price='100.00', yearly_price='900.00',
            max_employees=10, max_leads=100,
        )
        self.plan.refresh_from_db()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def make_checkout(self, billing_cycle, suffix):
        price = self.plan.monthly_price if billing_cycle == Subscription.BillingCycle.MONTHLY else self.plan.yearly_price
        return PlanCheckout.objects.create(
            plan=self.plan,
            organization=self.organization,
            billing_cycle=billing_cycle,
            purchaser_email=self.admin.email,
            amount=price,
            currency='INR',
            status=PlanCheckout.Status.PENDING,
            razorpay_order_id=f'order_{suffix}',
        )

    @patch('subscriptions.views.valid_checkout_signature', return_value=True)
    @patch('subscriptions.views.fetch_razorpay_payment')
    def test_monthly_and_yearly_captured_payments_activate_idempotently(self, fetch_payment, _signature):
        for expected_count, (cycle, suffix, payment_id, days) in enumerate((
            (Subscription.BillingCycle.MONTHLY, 'monthly', 'pay_monthly', 30),
            (Subscription.BillingCycle.YEARLY, 'yearly', 'pay_yearly', 365),
        ), start=1):
            checkout = self.make_checkout(cycle, suffix)
            fetch_payment.return_value = {
                'order_id': checkout.razorpay_order_id,
                'status': 'captured',
                'amount': int(checkout.amount * 100),
                'currency': 'INR',
            }
            payload = {
                'razorpay_order_id': checkout.razorpay_order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': 'test-signature',
            }

            response = self.client.post('/api/v1/subscriptions/checkout/verify/', payload, format='json')

            self.assertEqual(response.status_code, 200, response.data)
            checkout.refresh_from_db()
            self.assertEqual(checkout.status, PlanCheckout.Status.ACTIVATED)
            subscription = Subscription.objects.get(organization=self.organization, payment__provider_payment_id=payment_id)
            self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
            self.assertEqual(subscription.end_date - subscription.start_date, timedelta(days=days))
            self.assertEqual(Payment.objects.get(subscription=subscription).status, Payment.Status.SUCCEEDED)

            repeated = self.client.post('/api/v1/subscriptions/checkout/verify/', payload, format='json')
            self.assertEqual(repeated.status_code, 200, repeated.data)
            self.assertEqual(Subscription.objects.filter(organization=self.organization).count(), expected_count)
            self.assertEqual(Subscription.objects.filter(
                organization=self.organization,
                status=Subscription.Status.ACTIVE,
            ).count(), 1)

        self.assertEqual(fetch_payment.call_count, 2)

    @patch('subscriptions.views.valid_checkout_signature', return_value=True)
    @patch('subscriptions.views.fetch_razorpay_payment')
    def test_uncaptured_or_mismatched_payment_does_not_activate(self, fetch_payment, _signature):
        checkout = self.make_checkout(Subscription.BillingCycle.MONTHLY, 'mismatch')
        fetch_payment.return_value = {
            'order_id': checkout.razorpay_order_id,
            'status': 'captured',
            'amount': int(checkout.amount * 100) - 1,
            'currency': 'INR',
        }

        response = self.client.post(
            '/api/v1/subscriptions/checkout/verify/',
            {
                'razorpay_order_id': checkout.razorpay_order_id,
                'razorpay_payment_id': 'pay_mismatch',
                'razorpay_signature': 'test-signature',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Subscription.objects.filter(organization=self.organization).exists())
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, PlanCheckout.Status.PENDING)


@override_settings(
    ENTERPRISE_INQUIRY_ADMIN_EMAIL='sales-admin@example.test',
    DEFAULT_FROM_EMAIL='no-reply@example.test',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RAZORPAY_WEBHOOK_SECRET='test-webhook-secret',
    REST_FRAMEWORK={
        'DEFAULT_THROTTLE_RATES': {'enterprise_inquiry': '100/hour'},
    },
)
class EnterpriseInquiryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.payload = {
            'full_name': 'Asha Rao',
            'email': 'asha@example.test',
            'phone': '+91 98765 43210',
            'organization_name': 'Asha Finance',
            'website': 'https://asha.example.test',
            'linkedin_url': 'https://www.linkedin.com/in/asha-rao',
            'note': 'We need a custom deployment.',
        }

    def submit(self, payload=None, key=None):
        return self.client.post(
            '/api/v1/subscriptions/enterprise-inquiry/',
            payload if payload is not None else self.payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def test_valid_inquiry_saves_new_status_and_sends_exactly_two_emails(self):
        response = self.submit()

        self.assertEqual(response.status_code, 201, response.data)
        inquiry = EnterpriseInquiry.objects.get()
        self.assertEqual(inquiry.status, EnterpriseInquiry.Status.PENDING)
        self.assertTrue(inquiry.customer_email_sent)
        self.assertTrue(inquiry.admin_email_sent)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ['asha@example.test'])
        self.assertEqual(mail.outbox[1].to, ['sales-admin@example.test'])
        for value in self.payload.values():
            self.assertIn(value, mail.outbox[1].body)
        self.assertNotIn('sales-admin@example.test', str(response.data))
        self.assertEqual(PlanCheckout.objects.count(), 0)

    def test_inquiry_reads_are_not_public_and_admin_requires_authentication(self):
        self.assertEqual(self.client.get('/api/v1/subscriptions/enterprise-inquiry/').status_code, 405)
        admin_response = self.client.get('/admin/subscriptions/enterpriseinquiry/')
        self.assertEqual(admin_response.status_code, 302)

    def test_missing_fields_invalid_email_and_invalid_urls_are_rejected(self):
        cases = [
            ({key: value for key, value in self.payload.items() if key != 'phone'}, 'phone'),
            ({**self.payload, 'email': 'not-an-email'}, 'email'),
            ({**self.payload, 'website': 'javascript:alert(1)'}, 'website'),
            ({**self.payload, 'website': 'ftp://asha.example.test'}, 'website'),
            ({**self.payload, 'linkedin_url': 'not-a-url'}, 'linkedin_url'),
            ({**self.payload, 'phone': 'call-me-maybe'}, 'phone'),
        ]
        for payload, field in cases:
            response = self.submit(payload)
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn(field, response.data)
        self.assertEqual(EnterpriseInquiry.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_idempotency_retry_does_not_duplicate_inquiry_or_emails(self):
        key = uuid.uuid4()
        first = self.submit(key=key)
        second = self.submit(key=key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(EnterpriseInquiry.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_honeypot_is_accepted_without_storage_or_notifications(self):
        response = self.submit({**self.payload, 'fax': 'bot filled this'})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(EnterpriseInquiry.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    @patch('subscriptions.enterprise_workflow.send_mail', side_effect=OSError('smtp unavailable'))
    def test_email_failure_keeps_record_and_retry_does_not_resend(self, send_email):
        key = uuid.uuid4()
        first = self.submit(key=key)
        retry = self.submit(key=key)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data['email_delivery'], 'pending administrator review')
        self.assertEqual(retry.status_code, 200)
        inquiry = EnterpriseInquiry.objects.get()
        self.assertFalse(inquiry.customer_email_sent)
        self.assertFalse(inquiry.admin_email_sent)
        self.assertEqual(send_email.call_count, 2)

    @patch('subscriptions.enterprise_workflow.create_order')
    @patch('subscriptions.enterprise_workflow.send_mail', return_value=1)
    def test_admin_approved_quote_creates_enterprise_order_and_sends_short_lived_link(self, send_email, create_order):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload,
            status=EnterpriseInquiry.Status.AGREED,
            agreed_amount='125000.00',
            billing_cycle=Subscription.BillingCycle.YEARLY,
        )
        enterprise = Plan.objects.get(code='enterprise')
        create_order.return_value = ('rzp_test_key', {
            'id': 'order_enterprise_approved',
            'amount': 12500000,
            'currency': 'INR',
        })

        checkout = initiate_enterprise_checkout(inquiry.pk)

        self.assertEqual(checkout.plan, enterprise)
        self.assertEqual(checkout.amount, Decimal('125000.00'))
        self.assertEqual(checkout.status, PlanCheckout.Status.PENDING)
        self.assertTrue(checkout.enterprise_access_token_hash)
        self.assertGreater(checkout.enterprise_access_token_expires_at, timezone.now())
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, EnterpriseInquiry.Status.PAYMENT_INITIATED)
        self.assertIsNotNone(inquiry.payment_link_email_sent_at)
        create_order.assert_called_once_with(checkout)
        send_email.assert_called_once()
        self.assertIn('enterprise_checkout=', send_email.call_args.args[1])

    def test_public_checkout_cannot_buy_enterprise_even_if_enabled(self):
        enterprise = Plan.objects.get(code='enterprise')
        with override_settings(SUBSCRIPTION_CHECKOUT_ENABLED=True):
            response = self.client.post(
                '/api/v1/subscriptions/checkout/create/',
                {
                    'plan_id': str(enterprise.pk),
                    'billing_cycle': Subscription.BillingCycle.MONTHLY,
                    'email': 'asha@example.test',
                },
                format='json',
            )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('approved custom quote', response.data['detail'])
        self.assertEqual(PlanCheckout.objects.count(), 0)

    def test_enterprise_management_is_superuser_only_and_creates_recurring_plan_invitation(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload,
            status=EnterpriseInquiry.Status.APPROVED,
        )
        User = get_user_model()
        regular_admin = User.objects.create_user(username='regular-admin', password='test-password')
        self.client.force_authenticate(regular_admin)
        forbidden = self.client.get('/api/v1/subscriptions/enterprise/manage/')
        self.assertEqual(forbidden.status_code, 403)

        platform_admin = User.objects.create_superuser(
            username='platform-admin', email='platform@example.test', password='test-password',
        )
        self.client.force_authenticate(platform_admin)
        with patch('subscriptions.views.create_razorpay_plan', return_value={'id': 'plan_enterprise_test'}) as create_plan, \
                patch('subscriptions.views.create_razorpay_subscription', return_value=('rzp_test_key', {'id': 'sub_enterprise_test'})) as create_subscription:
            response = self.client.post(
                f'/api/v1/subscriptions/enterprise/manage/{inquiry.pk}/plan/',
                {
                    'name': 'Enterprise Custom',
                    'customer_email': inquiry.email,
                    'max_employees': 250,
                    'billing_cycle': 'MONTHLY',
                    'amount': '25000.00',
                    'currency': 'INR',
                    'duration_count': 24,
                    'features': {'audit_logs': True},
                    'storage_limit_mb': 50000,
                    'included_services': ['Migration', 'Priority support'],
                    'additional_services': 'Quarterly reviews',
                    'terms_conditions': 'Custom terms apply.',
                    'recurring': True,
                },
                format='json',
            )
            self.assertEqual(response.status_code, 201, response.data)
            plan = Plan.objects.get(pk=response.data['id'])
            inquiry.refresh_from_db()
            self.assertEqual(inquiry.status, EnterpriseInquiry.Status.PLAN_CREATED)
            self.assertEqual(plan.razorpay_plan_id, 'plan_enterprise_test')
            create_plan.assert_called_once()

            invitation = self.client.post(
                f'/api/v1/subscriptions/enterprise/manage/{inquiry.pk}/payment-invitation/',
                {}, format='json',
            )

        self.assertEqual(invitation.status_code, 201, invitation.data)
        self.assertEqual(invitation.data['payment_mode'], 'recurring')
        checkout = PlanCheckout.objects.get(enterprise_inquiry=inquiry)
        self.assertEqual(checkout.status, PlanCheckout.Status.PENDING_AUTHORIZATION)
        self.assertEqual(checkout.razorpay_subscription_id, 'sub_enterprise_test')
        self.assertTrue(checkout.enterprise_access_token_hash)
        self.assertTrue(inquiry.__class__.objects.get(pk=inquiry.pk).payment_link_email_sent_at)
        create_subscription.assert_called_once_with(checkout, total_count=24)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(str(checkout.pk), mail.outbox[0].body)

    @override_settings(RAZORPAY_KEY_ID='rzp_test_public_key')
    def test_enterprise_checkout_link_requires_valid_token(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload,
            status=EnterpriseInquiry.Status.PAYMENT_INITIATED,
            agreed_amount='5000.00',
            billing_cycle=Subscription.BillingCycle.MONTHLY,
        )
        raw_token = 'a-random-valid-test-token'
        checkout = PlanCheckout.objects.create(
            plan=Plan.objects.get(code='enterprise'),
            enterprise_inquiry=inquiry,
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            purchaser_email=inquiry.email,
            amount='5000.00',
            currency='INR',
            status=PlanCheckout.Status.PENDING,
            razorpay_order_id='order_enterprise_secure',
            enterprise_access_token_hash=hash_registration_token(raw_token),
            enterprise_access_token_expires_at=timezone.now() + timedelta(hours=1),
        )
        url = f'/api/v1/subscriptions/enterprise-checkout/{checkout.pk}/'

        invalid = self.client.get(url, {'token': 'wrong-token'})
        valid = self.client.get(url, {'token': raw_token})
        token_only = self.client.get('/api/v1/subscriptions/enterprise-checkout/', {'token': raw_token})

        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(valid.status_code, 200, valid.data)
        self.assertEqual(token_only.status_code, 200, token_only.data)
        self.assertEqual(valid.data['order_id'], 'order_enterprise_secure')
        self.assertEqual(valid.data['amount'], 500000)

    def test_enterprise_registration_link_is_sent_only_after_approved_payment(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload,
            status=EnterpriseInquiry.Status.AGREED,
            agreed_amount='5000.00',
            billing_cycle=Subscription.BillingCycle.MONTHLY,
        )
        with patch('subscriptions.enterprise_workflow.create_order') as create_order, \
                patch('subscriptions.enterprise_workflow.send_mail', return_value=1), \
                patch('subscriptions.webhooks.create_registration_token', return_value='registration-token-after-payment'), \
                patch('subscriptions.webhooks.send_registration_link') as send_registration_link:
            create_order.return_value = ('rzp_test_key', {
                'id': 'order_enterprise_registration', 'amount': 500000, 'currency': 'INR',
            })
            checkout = initiate_enterprise_checkout(inquiry.pk)
            send_registration_link.return_value = timezone.now()
            browser_callback = self.client.post(
                '/api/v1/subscriptions/checkout/verify/',
                {
                    'razorpay_order_id': checkout.razorpay_order_id,
                    'razorpay_payment_id': 'pay_enterprise_registration',
                    'razorpay_signature': 'browser-callback-is-not-source-of-truth',
                },
                format='json',
            )
            self.assertEqual(browser_callback.status_code, 202)
            self.assertEqual(send_registration_link.call_count, 0)
            checkout.refresh_from_db()
            self.assertEqual(checkout.status, PlanCheckout.Status.PENDING)
            raw_payload = json.dumps({
                'event': 'payment.captured',
                'payload': {'payment': {'entity': {
                    'id': 'pay_enterprise_registration',
                    'order_id': checkout.razorpay_order_id,
                    'status': 'captured',
                    'amount': 500000,
                    'currency': 'INR',
                }}, 'order': {'entity': {'id': checkout.razorpay_order_id}}},
            })
            payment_response = self.client.post(
                '/api/v1/subscriptions/webhooks/razorpay/',
                data=raw_payload,
                content_type='application/json',
                HTTP_X_RAZORPAY_EVENT_ID='evt_enterprise_registration',
                HTTP_X_RAZORPAY_SIGNATURE=hmac.new(b'test-webhook-secret', raw_payload.encode(), hashlib.sha256).hexdigest(),
            )

            self.assertEqual(payment_response.status_code, 200, payment_response.data)
            self.assertEqual(send_registration_link.call_count, 1)
            inquiry.refresh_from_db()
            self.assertEqual(inquiry.status, EnterpriseInquiry.Status.PAYMENT_INITIATED)
            self.assertFalse(Subscription.objects.filter(organization__slug='asha-finance').exists())

            registration_response = self.client.post(
                '/api/v1/organizations/register/',
                {
                    'registration_token': 'registration-token-after-payment',
                    'organization_name': 'Asha Finance',
                    'username': 'asha-enterprise',
                    'email': 'asha@example.test',
                    'password': 'ZebraHorse!754',
                    'confirm_password': 'ZebraHorse!754',
                    'first_name': 'Asha',
                    'last_name': 'Rao',
                },
                format='json',
            )

        self.assertEqual(registration_response.status_code, 201, registration_response.data)
        inquiry.refresh_from_db()
        checkout.refresh_from_db()
        self.assertEqual(inquiry.status, EnterpriseInquiry.Status.COMPLETED)
        self.assertEqual(checkout.status, PlanCheckout.Status.COMPLETED)
        self.assertEqual(Subscription.objects.filter(organization__slug='asha-finance').count(), 1)

    def test_recurring_activation_webhook_sends_registration_with_24_hour_lifetime_once(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload, status=EnterpriseInquiry.Status.PAYMENT_PENDING,
        )
        plan = Plan.objects.create(
            name='Custom Enterprise', code='custom-enterprise-webhook',
            monthly_price='5000.00', yearly_price=None, max_employees=100,
            razorpay_plan_id='plan_provider_enterprise', subscription_total_count=12,
        )
        inquiry.custom_plan = plan
        inquiry.save(update_fields=['custom_plan'])
        checkout = PlanCheckout.objects.create(
            plan=plan, enterprise_inquiry=inquiry,
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            purchaser_email=inquiry.email, customer_name=inquiry.full_name,
            amount='5000.00', currency='INR', payment_mode='recurring',
            status=PlanCheckout.Status.PENDING_AUTHORIZATION,
            razorpay_subscription_id='sub_provider_enterprise',
        )
        body = json.dumps({
            'event': 'subscription.activated',
            'payload': {'subscription': {'entity': {
                'id': 'sub_provider_enterprise', 'status': 'active',
            }}},
        })
        signature = hmac.new(b'test-webhook-secret', body.encode(), hashlib.sha256).hexdigest()
        with patch('subscriptions.webhooks.create_registration_token', return_value='enterprise-register-24h'), \
                patch('subscriptions.webhooks.send_registration_link', return_value=timezone.now()) as send_registration:
            response = self.client.post(
                '/api/v1/subscriptions/webhooks/razorpay/',
                data=body, content_type='application/json',
                HTTP_X_RAZORPAY_EVENT_ID='evt_enterprise_subscription_activated',
                HTTP_X_RAZORPAY_SIGNATURE=signature,
            )
            repeated = self.client.post(
                '/api/v1/subscriptions/webhooks/razorpay/',
                data=body, content_type='application/json',
                HTTP_X_RAZORPAY_EVENT_ID='evt_enterprise_subscription_activated',
                HTTP_X_RAZORPAY_SIGNATURE=signature,
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(repeated.data['status'], 'duplicate')
        self.assertEqual(send_registration.call_count, 1)
        self.assertEqual(send_registration.call_args.kwargs['lifetime'], timedelta(hours=24))
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, PlanCheckout.Status.PAID)
        self.assertEqual(checkout.duration_count, 1)

    def test_registration_details_are_token_scoped_and_admin_resend_rotates_the_token(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload, status=EnterpriseInquiry.Status.PAYMENT_PENDING,
        )
        plan = Plan.objects.create(
            name='Resend Enterprise', code='resend-enterprise-plan',
            monthly_price='1000.00', max_employees=25,
        )
        inquiry.custom_plan = plan
        inquiry.save(update_fields=['custom_plan'])
        old_token = 'old-enterprise-registration-token'
        checkout = PlanCheckout.objects.create(
            plan=plan, enterprise_inquiry=inquiry,
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            purchaser_email=inquiry.email, customer_name=inquiry.full_name,
            amount='1000.00', currency='INR', status=PlanCheckout.Status.PAID,
            registration_token_hash=hash_registration_token(old_token),
            registration_token_expires_at=timezone.now() + timedelta(hours=1),
        )
        details = self.client.get('/api/v1/subscriptions/registration-details/', {'token': old_token})
        self.assertEqual(details.status_code, 200, details.data)
        self.assertEqual(details.data['email'], inquiry.email)
        self.assertEqual(details.data['organization_name'], inquiry.organization_name)
        self.assertTrue(details.data['enterprise'])
        self.assertEqual(self.client.get('/api/v1/subscriptions/registration-details/', {'token': 'wrong'}).status_code, 404)

        User = get_user_model()
        admin_user = User.objects.create_superuser(username='resend-admin', email='resend-admin@example.test', password='test-password')
        self.client.force_authenticate(admin_user)
        with patch('subscriptions.views.create_registration_token', return_value='new-enterprise-registration-token'), \
                patch('subscriptions.views.send_registration_link', return_value=timezone.now()) as send_link:
            response = self.client.post(
                f'/api/v1/subscriptions/enterprise/manage/invitations/{checkout.pk}/resend-registration/',
                {}, format='json',
            )
        self.assertEqual(response.status_code, 200, response.data)
        send_link.assert_called_once()
        self.assertEqual(send_link.call_args.kwargs['lifetime'], timedelta(hours=24))
        checkout.refresh_from_db()
        self.assertNotEqual(checkout.registration_token_hash, hash_registration_token(old_token))
        self.assertEqual(self.client.get('/api/v1/subscriptions/registration-details/', {'token': old_token}).status_code, 404)
        new_details = self.client.get('/api/v1/subscriptions/registration-details/', {'token': 'new-enterprise-registration-token'})
        self.assertEqual(new_details.status_code, 200)

    def test_registration_email_delivery_failure_leaves_webhook_retryable(self):
        inquiry = EnterpriseInquiry.objects.create(
            **self.payload, status=EnterpriseInquiry.Status.PAYMENT_INITIATED,
            agreed_amount='5000.00', billing_cycle=Subscription.BillingCycle.MONTHLY,
        )
        checkout = PlanCheckout.objects.create(
            plan=Plan.objects.get(code='enterprise'), enterprise_inquiry=inquiry,
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            purchaser_email=inquiry.email, amount='5000.00', currency='INR',
            status=PlanCheckout.Status.PENDING, razorpay_order_id='order_email_retry',
        )
        raw_body = json.dumps({
            'event': 'payment.captured',
            'payload': {'payment': {'entity': {
                'id': 'pay_email_retry', 'order_id': checkout.razorpay_order_id,
                'status': 'captured', 'amount': 500000, 'currency': 'INR',
            }}},
        })
        signature = hmac.new(b'test-webhook-secret', raw_body.encode(), hashlib.sha256).hexdigest()
        with patch('subscriptions.webhooks.create_registration_token', return_value='email-retry-token'), \
                patch('subscriptions.webhooks.send_registration_link', side_effect=[RegistrationEmailError('smtp down'), timezone.now()]) as send_link:
            first = self.client.post(
                '/api/v1/subscriptions/webhooks/razorpay/', data=raw_body,
                content_type='application/json', HTTP_X_RAZORPAY_EVENT_ID='evt_email_retry',
                HTTP_X_RAZORPAY_SIGNATURE=signature,
            )
            event = RazorpayWebhookEvent.objects.get(event_id='evt_email_retry')
            self.assertIsNone(event.processed_at)
            second = self.client.post(
                '/api/v1/subscriptions/webhooks/razorpay/', data=raw_body,
                content_type='application/json', HTTP_X_RAZORPAY_EVENT_ID='evt_email_retry',
                HTTP_X_RAZORPAY_SIGNATURE=signature,
            )
        self.assertEqual(first.status_code, 500)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(send_link.call_count, 2)
        checkout.refresh_from_db()
        self.assertTrue(checkout.registration_email_sent_at)


class SubscriptionAccessStateTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Access State Org', slug='access-state-org')
        self.plan = Plan.objects.create(
            name='Limited plan', code='access-state-limited',
            monthly_price='100.00', yearly_price='1000.00',
            max_employees=1, max_leads=0,
        )

    def create_subscription(self, state, *, end_date=None):
        now = timezone.now()
        return Subscription.objects.create(
            organization=self.organization,
            plan=self.plan,
            Subscriptioncode='SUB-' + uuid.uuid4().hex[:12].upper(),
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            status=state,
            start_date=now - timedelta(days=1),
            end_date=end_date or now + timedelta(days=30),
        )

    def test_active_and_trial_subscriptions_enforce_lead_caps(self):
        for state in (Subscription.Status.ACTIVE, Subscription.Status.TRIALING):
            subscription = self.create_subscription(state)
            self.assertEqual(active_subscription(self.organization), subscription)
            with self.assertRaises(ValidationError):
                enforce_resource_limit(self.organization, 'leads')
            subscription.delete()

    def test_unpaid_expired_cancelled_and_missing_subscriptions_resolve_to_no_entitlement(self):
        # The API's existing behavior for this state is unlimited writes. The product owner
        # has not selected a deny, grace, or read-only policy, so this test records the gap.
        self.assertIsNone(active_subscription(self.organization))
        enforce_resource_limit(self.organization, 'leads')

        for state, end_date in (
            (Subscription.Status.PAST_DUE, timezone.now() + timedelta(days=1)),
            (Subscription.Status.CANCELLED, timezone.now() + timedelta(days=1)),
            (Subscription.Status.EXPIRED, timezone.now() + timedelta(days=1)),
            (Subscription.Status.ACTIVE, timezone.now() - timedelta(seconds=1)),
        ):
            self.create_subscription(state, end_date=end_date)
            self.assertIsNone(active_subscription(self.organization), state)
            enforce_resource_limit(self.organization, 'leads')
            Subscription.objects.all().delete()


class SubscriptionPlanManagementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username='superadmin_plans',
            email='superadmin_plans@example.test',
            password='testpassword123',
        )
        self.staff_user = User.objects.create_user(
            username='regular_staff_plans',
            email='regular_staff_plans@example.test',
            password='testpassword123',
        )
        self.starter, _ = Plan.objects.update_or_create(
            code='starter',
            defaults={
                'name': 'Starter',
                'monthly_price': Decimal('499.00'),
                'yearly_price': Decimal('4999.00'),
                'prices_confirmed': True,
                'max_employees': 5,
                'max_leads': 100,
                'features': {'lead_management': True},
                'is_active': True,
            }
        )
        self.growth, _ = Plan.objects.update_or_create(
            code='growth',
            defaults={
                'name': 'Growth',
                'monthly_price': Decimal('999.00'),
                'yearly_price': Decimal('9999.00'),
                'prices_confirmed': False,
                'max_employees': 20,
                'max_leads': 500,
                'features': {'lead_management': True},
                'is_active': True,
            }
        )
        self.client = APIClient()

    def test_anonymous_and_regular_user_cannot_manage_plans(self):
        # Anonymous
        response = self.client.get('/api/v1/subscriptions/manage/plans/')
        self.assertEqual(response.status_code, 401)
        # Regular user
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get('/api/v1/subscriptions/manage/plans/')
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_list_and_create_plans(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/v1/subscriptions/manage/plans/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(p['code'] == 'starter' for p in response.data))

        # Create completely new plan
        create_response = self.client.post('/api/v1/subscriptions/manage/plans/', {
            'name': 'Professional Plus',
            'code': 'professional-plus',
            'monthly_price': '1999.00',
            'yearly_price': '19999.00',
            'prices_confirmed': True,
            'max_employees': 50,
            'max_leads': 2000,
            'features': {'lead_management': True, 'ai_assistant': True},
            'is_active': True,
        }, format='json')
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data['code'], 'professional-plus')
        self.assertTrue(Plan.objects.filter(code='professional-plus').exists())

    def test_superuser_can_update_existing_plan(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f'/api/v1/subscriptions/manage/plans/{self.starter.id}/', {
            'name': 'Starter Updated',
            'monthly_price': '599.00',
            'max_employees': 10,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.starter.refresh_from_db()
        self.assertEqual(self.starter.name, 'Starter Updated')
        self.assertEqual(self.starter.monthly_price, Decimal('599.00'))
        self.assertEqual(self.starter.max_employees, 10)

    def test_checkout_settings_toggle_and_price_confirmation_validation(self):
        self.client.force_authenticate(user=self.admin)
        # Initially, Growth has unconfirmed prices, so enabling checkout should return 409 Conflict
        response = self.client.patch('/api/v1/subscriptions/manage/checkout-settings/', {
            'checkout_enabled': True,
        }, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(any(p['code'] == 'growth' for p in response.data.get('unconfirmed_plans', [])))

        # Confirm prices on all active plans
        Plan.objects.filter(is_active=True).exclude(code='enterprise').update(
            prices_confirmed=True,
            monthly_price=Decimal('999.00'),
            yearly_price=Decimal('9999.00'),
        )

        # Now enabling checkout should succeed
        enable_response = self.client.patch('/api/v1/subscriptions/manage/checkout-settings/', {
            'checkout_enabled': True,
        }, format='json')
        self.assertEqual(enable_response.status_code, 200)
        self.assertTrue(enable_response.data['checkout_enabled'])

        # And disabling checkout should succeed
        disable_response = self.client.patch('/api/v1/subscriptions/manage/checkout-settings/', {
            'checkout_enabled': False,
        }, format='json')
        self.assertEqual(disable_response.status_code, 200)
        self.assertFalse(disable_response.data['checkout_enabled'])

