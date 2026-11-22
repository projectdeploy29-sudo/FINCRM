from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from django.urls import reverse
from datetime import timedelta

from applications.models import ApplicationStatusHistory, FinancialApplication
from customers.models import Customer
from employes.models import Employee
from leads.models import Lead
from organizations.models import Organization
from subscriptions.models import Plan, Subscription


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
                "application_type": "Personal loan",
                "requested_amount": "125000.00",
                "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat(),
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

    def create_application(self):
        response = self.client.post(
            reverse("application-list"),
            {
                "customer": str(self.customer.id),
                "assigned_employee": str(self.employee.id),
                "application_type": "Personal loan",
                "requested_amount": "125000.00",
                "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def qualify(self, application_id):
        for next_status in ("under_review", "qualified"):
            response = self.client.post(
                reverse("application-transition", kwargs={"pk": application_id}),
                {"status": next_status},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)

    def test_application_status_history_records_and_returns_transitions(self):
        application = self.create_application()
        history_url = reverse("application-history", kwargs={"pk": application["id"]})

        response = self.client.get(history_url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["old_status"], "")
        self.assertEqual(response.data[0]["new_status"], FinancialApplication.Status.SUBMITTED)

        self.qualify(application["id"])

        response = self.client.get(history_url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [entry["new_status"] for entry in response.data],
            ["qualified", "under_review", "submitted"],
        )
        self.assertEqual(
            ApplicationStatusHistory.objects.filter(application_id=application["id"]).count(),
            3,
        )

    def test_qualified_application_creates_one_linked_lead_idempotently(self):
        application = self.create_application()
        self.qualify(application["id"])

        first = self.client.post(
            reverse("application-convert-to-lead", kwargs={"pk": application["id"]}),
            {}, format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        lead_id = first.data["lead"]["id"]
        lead = Lead.objects.get(pk=lead_id)
        self.assertEqual(str(lead.application_id), application["id"])
        self.assertEqual(lead.customer_id, self.customer.id)
        self.assertEqual(lead.assigned_to_id, self.employee.id)

        repeated = self.client.post(
            reverse("application-convert-to-lead", kwargs={"pk": application["id"]}),
            {}, format="json",
        )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data["lead_id"], str(lead_id))
        self.assertEqual(Lead.objects.filter(application_id=application["id"]).count(), 1)

        contact = self.client.post(
            reverse("lead-transition", kwargs={"pk": str(lead_id)}),
            {"status": "contacted"}, format="json",
        )
        self.assertEqual(contact.status_code, 200, contact.data)
        premature_qualification = self.client.post(
            reverse("lead-transition", kwargs={"pk": str(lead_id)}),
            {"status": "qualified"}, format="json",
        )
        self.assertEqual(premature_qualification.status_code, 400, premature_qualification.data)
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.CONTACTED)

    def test_conversion_enforces_active_subscription_lead_limit(self):
        application = self.create_application()
        self.qualify(application["id"])
        plan = Plan.objects.create(
            name="No leads plan", code="no-leads-plan", monthly_price="0.00",
            max_employees=10, max_leads=0,
        )
        now = timezone.now()
        Subscription.objects.create(
            organization=self.organization, plan=plan, Subscriptioncode="NO-LEADS-SUB",
            billing_cycle=Subscription.BillingCycle.MONTHLY,
            status=Subscription.Status.ACTIVE, start_date=now,
            end_date=now + timedelta(days=30),
        )

        response = self.client.post(
            reverse("application-convert-to-lead", kwargs={"pk": application["id"]}),
            {}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Lead.objects.filter(application_id=application["id"]).exists())
