from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.utils import timezone
from organizations.models import organizations_organization
from subscriptions.models import Plan, PlanCheckout, Subscription
from subscriptions.registration import create_registration_token, hash_registration_token
from aron_fincrm.settings import _database_config

User = get_user_model()


class DatabaseConfigurationTests(SimpleTestCase):
    def test_sqlite_remains_the_default_backend(self):
        database = _database_config({})['default']
        self.assertEqual(database['ENGINE'], 'django.db.backends.sqlite3')
        self.assertTrue(str(database['NAME']).endswith('db.sqlite3'))

    def test_postgresql_is_opt_in_and_uses_connection_health_checks(self):
        database = _database_config({
            'DB_ENGINE': 'postgresql',
            'DB_NAME': 'fincrm_test',
            'DB_USER': 'fincrm_test_user',
            'DB_PASSWORD': 'test-only-password',
            'DB_HOST': 'db.example.test',
        })['default']
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(database['PORT'], '5432')
        self.assertEqual(database['CONN_MAX_AGE'], 60)
        self.assertTrue(database['CONN_HEALTH_CHECKS'])
        self.assertEqual(database['OPTIONS'], {'sslmode': 'require'})

    def test_postgresql_requires_explicit_connection_settings(self):
        with self.assertRaises(ImproperlyConfigured):
            _database_config({'DB_ENGINE': 'postgresql'})

    def test_invalid_database_engine_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            _database_config({'DB_ENGINE': 'mysql'})


class Stage1FoundationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Seed permissions and roles
        call_command('seed_roles_permissions')

    def test_organization_registration(self):
        """
        Verify that a new organization can register with an Org Admin user,
        returning valid JWT tokens and user metadata.
        """
        payload = {
            "registration_token": "",
            "organization_name": "Apex Finance Corp",
            "legal_name": "Apex Finance Corporation Pvt Ltd",
            "org_email": "contact@apexfinance.com",
            "org_phone": "+919876543210",
            "city": "Mumbai",
            "state": "Maharashtra",
            "currency": "INR",
            "username": "apexadmin",
            "email": "admin@apexfinance.com",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "first_name": "Raj",
            "last_name": "Malhotra",
        }
        plan = Plan.objects.create(
            name="Registration test plan", code="registration-test-plan",
            monthly_price="1234.00", max_employees=10, max_leads=100,
        )
        registration_token = create_registration_token()
        now = timezone.now()
        PlanCheckout.objects.create(
            plan=plan,
            billing_cycle="MONTHLY",
            purchaser_email=payload['email'],
            amount="1234.00",
            currency="INR",
            status=PlanCheckout.Status.PAID,
            razorpay_order_id="order_registration_test",
            razorpay_payment_id="pay_registration_test",
            registration_token_hash=hash_registration_token(registration_token),
            registration_token_expires_at=now + timedelta(hours=1),
            paid_at=now,
        )
        payload['registration_token'] = registration_token
        response = self.client.post(reverse('organization_register'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('tokens', data)
        self.assertIn('access', data['tokens'])
        self.assertIn('refresh', data['tokens'])
        self.assertIn('organization', data)
        self.assertEqual(data['organization']['name'], "Apex Finance Corp")
        self.assertEqual(data['user']['username'], "apexadmin")

        # Verify DB creation
        self.assertTrue(organizations_organization.objects.filter(name="Apex Finance Corp").exists())
        user = User.objects.get(username="apexadmin")
        self.assertIsNotNone(user.default_organization)
        self.assertEqual(user.default_organization.name, "Apex Finance Corp")
        self.assertEqual(Subscription.objects.get(organization=user.default_organization).plan, plan)

    def test_jwt_login_and_me_endpoint(self):
        """
        Verify that login returns customized JWT tokens and /api/v1/auth/me/
        correctly resolves the user's organizational and RBAC context.
        """
        # Register org
        org = organizations_organization.objects.create(
            name="Horizon Finserv",
            slug="horizon-finserv",
            email="info@horizon.com",
            currency="INR"
        )
        user = User.objects.create_user(
            username="horizonadmin",
            email="admin@horizon.com",
            password="SecurePassword123",
            first_name="Anita",
            last_name="Desai",
            default_organization=org,
        )

        # Login
        login_response = self.client.post(
            reverse('auth_login'),
            {"username": "horizonadmin", "password": "SecurePassword123"},
            format='json'
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        login_data = login_response.json()
        self.assertIn('access', login_data)
        self.assertIn('refresh', login_data)
        self.assertEqual(login_data['role']['code'], 'org_admin')
        self.assertEqual(login_data['organization']['id'], str(org.id))

        # Access /api/v1/auth/me/ with Bearer token
        access_token = login_data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_response = self.client.get(reverse('auth_me'))
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        me_data = me_response.json()
        self.assertEqual(me_data['username'], "horizonadmin")
        self.assertEqual(me_data['organization']['name'], "Horizon Finserv")
        self.assertEqual(me_data['role']['code'], "org_admin")
        self.assertGreaterEqual(len(me_data['permissions']), 1)

    def test_refresh_rotation_and_logout_revoke_refresh_tokens(self):
        org = organizations_organization.objects.create(name='Logout Org', slug='logout-org')
        user = User.objects.create_user(
            username='logout_user',
            password='SecurePassword123',
            default_organization=org,
        )
        login = self.client.post(
            reverse('auth_login'),
            {'username': user.username, 'password': 'SecurePassword123'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        old_refresh = login.data['refresh']

        refreshed = APIClient().post(
            reverse('auth_token_refresh'),
            {'refresh': old_refresh},
            format='json',
        )
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK, refreshed.data)
        new_refresh = refreshed.data['refresh']
        replay = APIClient().post(
            reverse('auth_token_refresh'),
            {'refresh': old_refresh},
            format='json',
        )
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

        logout = APIClient().post(reverse('auth_logout'), {'refresh': new_refresh}, format='json')
        self.assertEqual(logout.status_code, status.HTTP_205_RESET_CONTENT)
        after_logout = APIClient().post(
            reverse('auth_token_refresh'),
            {'refresh': new_refresh},
            format='json',
        )
        self.assertEqual(after_logout.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_organization_endpoint(self):
        """
        Verify that GET /api/v1/organizations/current/ returns the active tenant profile
        and PATCH updates organization settings for Org Admin.
        """
        org = organizations_organization.objects.create(
            name="Bharat Lending Co",
            slug="bharat-lending",
            currency="INR"
        )
        user = User.objects.create_user(
            username="bharatadmin",
            password="Password123",
            default_organization=org,
            is_staff=True
        )

        login_res = self.client.post(reverse('auth_login'), {"username": "bharatadmin", "password": "Password123"})
        token = login_res.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # GET current org
        get_res = self.client.get(reverse('organization_current'))
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.json()['name'], "Bharat Lending Co")

        # PATCH current org
        patch_res = self.client.patch(
            reverse('organization_current'),
            {"phone": "+919999988888", "city": "Bengaluru"},
            format='json'
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.json()['phone'], "+919999988888")
        self.assertEqual(patch_res.json()['city'], "Bengaluru")
