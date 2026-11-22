import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from organizations.models import organizations_organization
from permitions.models import Role
from subscriptions.models import Plan, Subscription


class CustomRoleEntitlementTests(TestCase):
    def setUp(self):
        self.organization = organizations_organization.objects.create(
            name='Entitlement Org', slug='entitlement-org',
        )
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='entitlement-admin',
            email='entitlement-admin@example.test',
            password='test-password',
            default_organization=self.organization,
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.starter = Plan.objects.create(
            name='Starter', code='custom-role-starter',
            monthly_price='100.00', yearly_price='1000.00',
            features={'custom_roles': False},
        )
        now = timezone.now()
        self.subscription = Subscription.objects.create(
            organization=self.organization,
            plan=self.starter,
            Subscriptioncode='SUB-' + uuid.uuid4().hex[:12].upper(),
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=now,
            end_date=now + timedelta(days=30),
        )

    def test_starter_cannot_create_custom_roles_through_api(self):
        response = self.client.post(
            '/api/v1/roles/',
            {'name': 'Custom Sales', 'code': 'custom-sales'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('subscription', response.data)
        self.assertFalse(Role.objects.filter(organization=self.organization).exists())

    def test_enterprise_feature_flag_allows_custom_role_creation(self):
        enterprise = Plan.objects.create(
            name='Enterprise', code='custom-role-enterprise',
            monthly_price=None, yearly_price=None,
            features={'custom_roles': True},
        )
        self.subscription.plan = enterprise
        self.subscription.save(update_fields=['plan'])

        response = self.client.post(
            '/api/v1/roles/',
            {'name': 'Custom Sales', 'code': 'custom-sales'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Role.objects.filter(organization=self.organization, code='custom-sales').exists())
