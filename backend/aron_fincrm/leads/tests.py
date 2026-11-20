from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from organizations.models import organizations_organization, Department, Team
from accounts.models import Manager
from employes.models import Employee
from permitions.models import Role
from leads.models import Lead, LeadAssignmentHistory
from customers.models import Customer, CustomerTag

User = get_user_model()


class Stage3CRMCoreTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        call_command('seed_roles_permissions')
        call_command('seed_plans')

        # 1. Organization & Org Admin
        self.org = organizations_organization.objects.create(
            name="Apex Capital Finance",
            slug="apex-capital",
            currency="INR"
        )
        self.admin_user = User.objects.create_user(
            username="apex_owner",
            email="owner@apexcapital.com",
            password="Password123",
            default_organization=self.org,
            is_staff=True,
        )

        login_res = self.client.post(
            reverse('auth_login'),
            {"username": "apex_owner", "password": "Password123"}
        )
        self.admin_token = login_res.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')

        # 2. Department & Manager
        self.dept = Department.objects.create(organization=self.org, name="Loan Sales")
        self.mgr_user = User.objects.create_user(
            username="apex_mgr",
            email="mgr@apexcapital.com",
            password="Password123",
            default_organization=self.org,
        )
        self.manager = Manager.objects.create(
            organization=self.org,
            user=self.mgr_user,
            code="MGR01",
            work_email="mgr@apexcapital.com",
        )
        self.dept.manager = self.manager
        self.dept.save()

        # 3. Employee (Loan Officer)
        self.emp_user = User.objects.create_user(
            username="apex_emp",
            email="emp@apexcapital.com",
            password="Password123",
            default_organization=self.org,
        )
        self.general_role = Role.objects.get(code='general_employee')
        self.employee = Employee.objects.create(
            organization=self.org,
            user=self.emp_user,
            employee_code="EMP01",
            department=self.dept,
            role=self.general_role,
            work_email="emp@apexcapital.com",
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )

    def test_lead_creation_and_listing(self):
        """
        Leads may only be created from qualified financial applications.
        """
        payload = {
            "contact_name": "Vikram Sethi",
            "phone": "+919876543210",
            "email": "vikram@example.com",
            "city": "Pune",
            "state": "Maharashtra",
            "source": "website",
            "priority": "HIGH",
            "expected_amount": 750000.00,
        }
        res = self.client.post(reverse('lead-list'), payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Lead.objects.count(), 0)

        # Verify listing
        list_res = self.client.get(reverse('lead-list'))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.json()['results']), 0)

    def test_lead_assignment_workflow(self):
        """
        Verify Manager assigns lead to an Employee and history is recorded.
        """
        lead = Lead.objects.create(
            organization=self.org,
            lead_code="LEAD-1001",
            contact_name="Sunil Gavaskar",
            phone="+919811122233",
            source="referral",
            priority="HIGH",
            status="new",
        )

        assign_res = self.client.post(
            reverse('lead-assign', kwargs={'pk': str(lead.id)}),
            {"employee_id": str(self.employee.id), "reason": "Assigned high-value lead for home loan"},
            format='json'
        )
        self.assertEqual(assign_res.status_code, status.HTTP_200_OK, assign_res.data)

        # Check DB update
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, self.employee)

        # Check assignment history endpoint
        hist_res = self.client.get(reverse('lead-history', kwargs={'pk': str(lead.id)}))
        self.assertEqual(hist_res.status_code, status.HTTP_200_OK)
        history_list = hist_res.json()
        self.assertEqual(len(history_list), 1)
        self.assertEqual(history_list[0]['new_owner'], str(self.employee.id))
        self.assertEqual(history_list[0]['reason'], "Assigned high-value lead for home loan")

    def test_lead_conversion_to_customer(self):
        """
        Lead-to-customer conversion is retired; qualified applications are the
        only supported source of leads.
        """
        lead = Lead.objects.create(
            organization=self.org,
            lead_code="LEAD-2002",
            contact_name="Ramesh Gupta",
            phone="+919822233344",
            email="ramesh.gupta@example.com",
            city="Jaipur",
            state="Rajasthan",
            source="walk_in",
            priority="HIGH",
            status="qualified",
            assigned_to=self.employee,
        )

        convert_payload = {
            "customer_type": "INDIVIDUAL",
            "address_line1": "42 Malviya Nagar",
            "city": "Jaipur",
            "state": "Rajasthan",
            "pin_code": "302017",
            "tag": "VIP",
        }
        res = self.client.post(
            reverse('lead-convert', kwargs={'pk': str(lead.id)}),
            convert_payload,
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        self.assertFalse(Customer.objects.filter(primary_phone="+919822233344").exists())

    def test_customer_lifecycle_timeline_excludes_removed_conversations(self):
        """Verify new customer timelines no longer include conversation records."""
        # 1. Create Customer
        cust_res = self.client.post(
            reverse('customer-list'),
            {
                "customer_type": "INDIVIDUAL",
                "full_name": "Pooja Hegde",
                "primary_phone": "+919877766655",
                "email": "pooja@example.com",
                "city": "Hyderabad",
                "preferred_channel": "phone",
                "tag_list": ["VIP", "General"],
            },
            format='json'
        )
        self.assertEqual(cust_res.status_code, status.HTTP_201_CREATED)
        customer_id = cust_res.json()['id']

        # 2. Request Customer Timeline
        timeline_res = self.client.get(
            reverse('customer-timeline', kwargs={'pk': customer_id})
        )
        self.assertEqual(timeline_res.status_code, status.HTTP_200_OK)
        timeline_data = timeline_res.json()
        self.assertEqual(timeline_data['total_events'], 0)
        self.assertEqual(timeline_data['timeline'], [])
