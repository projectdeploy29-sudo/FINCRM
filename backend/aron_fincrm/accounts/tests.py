from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from organizations.models import organizations_organization
from organizations.tenant import get_user_organization, get_user_role_context

User = get_user_model()


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
            "first_name": "Raj",
            "last_name": "Malhotra",
        }
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
