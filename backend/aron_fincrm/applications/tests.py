from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse

from customers.models import Customer
from employes.models import Employee
from organizations.models import Organization
from subscriptions.models import Plan


class ApplicationCreationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(name="Test Org", slug="test-org")
        self.admin = User.objects.create_user(
            username="test_admin",
            password="test-password",
            default_organization=self.organization,
        )
        self.employee_user = User.objects.create_user(
            username="test_employee",
            password="test-password",
            default_organization=self.organization,
        )
        self.employee = Employee.objects.create(
            organization=self.organization,
            user=self.employee_user,
            employee_code="TEST-EMP-001",
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            customer_code="TEST-CUST-001",
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Test Customer",
            primary_phone="9000000000",
            preferred_channel=Customer.PreferredChannel.PHONE,
            status=Customer.Status.PROSPECT,
            assigned_to=self.employee,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_application_can_be_created_without_manually_entering_its_code(self):
        response = self.client.post(
            reverse("application-list"),
            {
                "customer": str(self.customer.id),
                "assigned_employee": str(self.employee.id),
                "requested_amount": "125000.00",
                "currency": "INR",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["application_code"].startswith("APP-"))

    def test_public_plan_page_endpoint_returns_database_plans(self):
        Plan.objects.create(
            name="Test Plan",
            code="test-plan",
            monthly_price="1234.00",
            max_employees=10,
            max_leads=25,
            daily_ai_tokens=500,
            is_active=True,
        )

        response = APIClient().get("/api/v1/subscriptions/plans/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["code"], "test-plan")

    def test_pipeline_and_report_endpoints_are_registered_at_api_root(self):
        pipeline_response = self.client.get("/api/v1/pipeline/")
        report_response = self.client.get("/api/v1/reports/summary/")

        self.assertEqual(pipeline_response.status_code, 200, pipeline_response.data)
        self.assertEqual(report_response.status_code, 200, report_response.data)
