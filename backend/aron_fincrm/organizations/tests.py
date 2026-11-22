from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Manager, TeamLead
from applications.models import FinancialApplication
from customers.models import Customer, CustomerAssignmentHistory
from employes.models import Employee
from leads.models import Lead
from organizations.models import Department, Organization, Team
from organizations.date_filters import apply_date_range
from subscriptions.models import Plan, Subscription
from tasks.models import Task
from permitions.models import Role


class OrganizationIsolationTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Northwind", slug="northwind")
        self.org_b = Organization.objects.create(name="Contoso", slug="contoso")

        self.admin_a = self.make_user("northwind_admin", self.org_a)
        self.admin_b = self.make_user("contoso_admin", self.org_b)

        self.manager_a, self.department_a = self.make_manager(
            "northwind_manager", self.org_a, "East", "NW-MGR-E"
        )
        self.manager_b, self.department_b = self.make_manager(
            "northwind_manager_west", self.org_a, "West", "NW-MGR-W"
        )
        self.manager_c, self.department_c = self.make_manager(
            "contoso_manager", self.org_b, "Contoso East", "CO-MGR-E"
        )

        self.teamlead_a = self.make_teamlead(
            "northwind_teamlead", self.org_a, self.department_a, self.manager_a, "NW-TL-E"
        )
        self.teamlead_b = self.make_teamlead(
            "northwind_teamlead_west", self.org_a, self.department_b, self.manager_b, "NW-TL-W"
        )
        self.teamlead_c = self.make_teamlead(
            "contoso_teamlead", self.org_b, self.department_c, self.manager_c, "CO-TL-E"
        )

        self.team_a = self.make_team(self.org_a, self.department_a, self.teamlead_a, "East Team")
        self.team_b = self.make_team(self.org_a, self.department_b, self.teamlead_b, "West Team")
        self.team_c = self.make_team(self.org_b, self.department_c, self.teamlead_c, "Contoso East Team")

        self.employee_a1 = self.make_employee(
            "northwind_employee_1", self.org_a, self.department_a, self.team_a, "NW-E-1"
        )
        self.employee_a2 = self.make_employee(
            "northwind_employee_2", self.org_a, self.department_a, self.team_a, "NW-E-2"
        )
        self.employee_b = self.make_employee(
            "northwind_employee_west", self.org_a, self.department_b, self.team_b, "NW-W-1"
        )
        self.employee_c = self.make_employee(
            "contoso_employee", self.org_b, self.department_c, self.team_c, "CO-E-1"
        )

        self.customer_a1, self.lead_a1, self.application_a1 = self.make_work(
            self.org_a, self.employee_a1, "NW-E-1"
        )
        self.customer_a2, self.lead_a2, self.application_a2 = self.make_work(
            self.org_a, self.employee_a2, "NW-E-2"
        )
        self.customer_b, self.lead_b, self.application_b = self.make_work(
            self.org_a, self.employee_b, "NW-W-1"
        )
        self.customer_c, self.lead_c, self.application_c = self.make_work(
            self.org_b, self.employee_c, "CO-E-1"
        )

        self.task_a = self.make_task(self.org_a, self.employee_a1, "NW-EAST-TASK")
        self.task_a2 = self.make_task(self.org_a, self.employee_a2, "NW-EAST-TASK-2")
        self.task_b = self.make_task(self.org_a, self.employee_b, "NW-WEST-TASK")
        self.task_c = self.make_task(self.org_b, self.employee_c, "CO-EAST-TASK")

        self.plan = Plan.objects.create(
            name="Isolation test plan",
            code="isolation-test-plan",
            monthly_price="1.00",
            max_employees=8,
            max_leads=3,
        )
        now = timezone.now()
        for organization, code in ((self.org_a, "NW-TEST-SUB"), (self.org_b, "CO-TEST-SUB")):
            Subscription.objects.create(
                organization=organization,
                plan=self.plan,
                Subscriptioncode=code,
                billing_cycle=Subscription.BillingCycle.MONTHLY,
                status=Subscription.Status.ACTIVE,
                start_date=now,
                end_date=now + timedelta(days=30),
            )

    @staticmethod
    def make_user(username, organization):
        User = get_user_model()
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password="test-password",
            default_organization=organization,
        )

    def make_manager(self, username, organization, department_name, code):
        user = self.make_user(username, organization)
        manager = Manager.objects.create(
            organization=organization,
            user=user,
            code=code,
            employment_status=Manager.ManagerStatus.ACTIVE,
        )
        department = Department.objects.create(
            organization=organization,
            manager=manager,
            name=department_name,
        )
        return manager, department

    def make_teamlead(self, username, organization, department, manager, code):
        user = self.make_user(username, organization)
        return TeamLead.objects.create(
            organization=organization,
            user=user,
            department=department,
            manager=manager,
            code=code,
            employment_status=TeamLead.teamStatus.ACTIVE,
        )

    @staticmethod
    def make_team(organization, department, teamlead, name):
        return Team.objects.create(
            organization=organization,
            department=department,
            team_lead=teamlead,
            name=name,
        )

    def make_employee(self, username, organization, department, team, code):
        user = self.make_user(username, organization)
        return Employee.objects.create(
            organization=organization,
            user=user,
            department=department,
            team=team,
            employee_code=code,
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )

    @staticmethod
    def make_work(organization, employee, prefix):
        states = {
            "NW-E-1": "Maharashtra",
            "NW-E-2": "Goa",
            "NW-W-1": "Karnataka",
            "CO-E-1": "Gujarat",
        }
        lead_statuses = {
            "NW-E-1": Lead.Status.NEW,
            "NW-E-2": Lead.Status.CONTACTED,
            "NW-W-1": Lead.Status.QUALIFIED,
            "CO-E-1": Lead.Status.UNQUALIFIED,
        }
        customer = Customer.objects.create(
            organization=organization,
            customer_code=f"{prefix}-CUSTOMER",
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name=f"{prefix} Customer",
            primary_phone="9000000000",
            city=f"{prefix} City",
            state=states[prefix],
            preferred_channel=Customer.PreferredChannel.PHONE,
            status=Customer.Status.ACTIVE,
            created_by=employee,
            assigned_to=employee,
        )
        lead = Lead.objects.create(
            organization=organization,
            lead_code=f"{prefix}-LEAD",
            contact_name=f"{prefix} Lead",
            phone="9000000000",
            city=f"{prefix} City",
            state=states[prefix],
            status=lead_statuses[prefix],
            expected_amount="100000.00",
            created_by=employee,
            assigned_to=employee,
            converted_customer=customer,
        )
        application = FinancialApplication.objects.create(
            organization=organization,
            application_code=f"{prefix}-APP",
            customer=customer,
            lead=lead,
            assigned_employee=employee,
            requested_amount="100000.00",
        )
        return customer, lead, application

    @staticmethod
    def make_task(organization, employee, title):
        return Task.objects.create(
            organization=organization,
            title=title,
            assigned_to=employee,
            assigned_to_user=employee.user,
            department=employee.department,
            team=employee.team,
            due_date=timezone.now() + timedelta(days=1),
        )

    def client_for(self, user, organization_header=None):
        client = APIClient()
        client.force_authenticate(user)
        if organization_header:
            client.credentials(HTTP_X_ORGANIZATION_ID=str(organization_header))
        return client

    def rows(self, client, path, expected_status=200):
        response = client.get(path)
        self.assertEqual(response.status_code, expected_status, getattr(response, "data", None))
        data = getattr(response, "data", None)
        return data.get("results", data) if isinstance(data, dict) else data

    def test_organization_admins_cannot_list_or_open_other_organizations_records(self):
        client_a = self.client_for(self.admin_a)
        client_b = self.client_for(self.admin_b)

        for path, own_code, other_code in (
            ("/api/v1/leads/", self.lead_a1.lead_code, self.lead_c.lead_code),
            ("/api/v1/customers/", self.customer_a1.customer_code, self.customer_c.customer_code),
            ("/api/v1/applications/", self.application_a1.application_code, self.application_c.application_code),
            ("/api/v1/tasks/", self.task_a.title, self.task_c.title),
            ("/api/v1/staff/employees/", self.employee_a1.employee_code, self.employee_c.employee_code),
            ("/api/v1/staff/managers/", self.manager_a.code, self.manager_c.code),
            ("/api/v1/staff/team-leads/", self.teamlead_a.code, self.teamlead_c.code),
            ("/api/v1/organizations/departments/", self.department_a.name, self.department_c.name),
            ("/api/v1/organizations/teams/", self.team_a.name, self.team_c.name),
        ):
            own_rows = self.rows(client_a, path)
            other_rows = self.rows(client_b, path)
            own_values = {str(value) for row in own_rows for value in row.values()}
            other_values = {str(value) for row in other_rows for value in row.values()}
            self.assertIn(own_code, own_values, path)
            self.assertNotIn(other_code, own_values, path)
            self.assertIn(other_code, other_values, path)
            self.assertNotIn(own_code, other_values, path)

        for path, record_id in (
            ("/api/v1/leads/", self.lead_c.id),
            ("/api/v1/customers/", self.customer_c.id),
            ("/api/v1/applications/", self.application_c.id),
            ("/api/v1/tasks/", self.task_c.id),
            ("/api/v1/staff/employees/", self.employee_c.id),
        ):
            self.rows(client_a, f"{path}{record_id}/", expected_status=404)

        # A tenant cannot switch to another organization by supplying its ID.
        header_client = self.client_for(self.admin_a, self.org_b.id)
        header_rows = self.rows(header_client, "/api/v1/leads/")
        self.assertEqual({row["lead_code"] for row in header_rows}, {
            self.lead_a1.lead_code, self.lead_a2.lead_code, self.lead_b.lead_code
        })
        customer_rows_a = self.rows(client_a, "/api/v1/customers/")
        customer_rows_b = self.rows(client_b, "/api/v1/customers/")
        self.assertNotIn("Gujarat", {row["state"] for row in customer_rows_a})
        self.assertEqual({row["state"] for row in customer_rows_b}, {"Gujarat"})

    def test_manager_teamlead_and_employee_data_stays_in_reporting_scope(self):
        manager_client = self.client_for(self.manager_a.user)
        teamlead_client = self.client_for(self.teamlead_a.user)
        employee_client = self.client_for(self.employee_a1.user)

        manager_leads = self.rows(manager_client, "/api/v1/leads/")
        self.assertEqual({row["lead_code"] for row in manager_leads}, {
            self.lead_a1.lead_code, self.lead_a2.lead_code
        })
        teamlead_leads = self.rows(teamlead_client, "/api/v1/leads/")
        self.assertEqual({row["lead_code"] for row in teamlead_leads}, {
            self.lead_a1.lead_code, self.lead_a2.lead_code
        })
        employee_leads = self.rows(employee_client, "/api/v1/leads/")
        self.assertEqual({row["lead_code"] for row in employee_leads}, {self.lead_a1.lead_code})

        manager_employees = self.rows(manager_client, "/api/v1/staff/employees/")
        self.assertEqual({row["employee_code"] for row in manager_employees}, {
            self.employee_a1.employee_code, self.employee_a2.employee_code
        })
        teamlead_employees = self.rows(teamlead_client, "/api/v1/staff/employees/")
        self.assertEqual({row["employee_code"] for row in teamlead_employees}, {
            self.employee_a1.employee_code, self.employee_a2.employee_code
        })
        employee_rows = self.rows(employee_client, "/api/v1/staff/employees/")
        self.assertEqual({row["employee_code"] for row in employee_rows}, {self.employee_a1.employee_code})

        manager_tasks = self.rows(manager_client, "/api/v1/tasks/")
        self.assertEqual({row["title"] for row in manager_tasks}, {self.task_a.title, self.task_a2.title})
        teamlead_tasks = self.rows(teamlead_client, "/api/v1/tasks/")
        self.assertEqual({row["title"] for row in teamlead_tasks}, {self.task_a.title, self.task_a2.title})
        employee_tasks = self.rows(employee_client, "/api/v1/tasks/")
        self.assertEqual({row["title"] for row in employee_tasks}, {self.task_a.title})

        manager_pipeline = manager_client.get("/api/v1/pipeline/")
        teamlead_pipeline = teamlead_client.get("/api/v1/pipeline/")
        employee_pipeline = employee_client.get("/api/v1/pipeline/")
        self.assertEqual(manager_pipeline.status_code, 200)
        self.assertEqual(teamlead_pipeline.status_code, 200)
        self.assertEqual(employee_pipeline.status_code, 200)
        self.assertEqual({row["lead_code"] for row in manager_pipeline.data["leads"]}, {
            self.lead_a1.lead_code, self.lead_a2.lead_code
        })
        self.assertEqual({row["lead_code"] for row in teamlead_pipeline.data["leads"]}, {
            self.lead_a1.lead_code, self.lead_a2.lead_code
        })
        self.assertEqual({row["lead_code"] for row in employee_pipeline.data["leads"]}, {self.lead_a1.lead_code})
        self.assertEqual({row["status"] for row in manager_pipeline.data["leads"]}, {
            Lead.Status.NEW, Lead.Status.CONTACTED
        })
        admin_b_pipeline = self.client_for(self.admin_b).get("/api/v1/pipeline/")
        self.assertEqual({row["status"] for row in admin_b_pipeline.data["leads"]}, {Lead.Status.UNQUALIFIED})

    def test_active_role_header_cannot_elevate_employee_scope(self):
        sales_role = Role.objects.create(
            organization=self.org_a,
            name="Sales Specialist",
            code="sales_specialist",
        )
        self.employee_a1.additional_roles.add(sales_role)
        client = self.client_for(self.employee_a1.user)

        client.credentials(HTTP_X_ACTIVE_ROLE="sales_specialist")
        pipeline = client.get("/api/v1/pipeline/")
        self.assertEqual(pipeline.status_code, 200, pipeline.data)
        self.assertEqual({row["lead_code"] for row in pipeline.data["leads"]}, {self.lead_a1.lead_code})

        client.credentials(HTTP_X_ACTIVE_ROLE="org_admin")
        admin_dashboard = client.get("/api/v1/dashboards/admin/")
        self.assertEqual(admin_dashboard.status_code, 403, admin_dashboard.data)

    def test_inactive_employee_profile_cannot_use_tenant_endpoints(self):
        self.employee_a1.employment_status = Employee.EmploymentStatus.TERMINATED
        self.employee_a1.save(update_fields=['employment_status'])
        response = self.client_for(self.employee_a1.user).get('/api/v1/leads/')
        self.assertEqual(response.status_code, 403, response.data)

    def test_assignment_dropdowns_only_return_active_managers_and_team_leads(self):
        self.manager_b.employment_status = Manager.ManagerStatus.ON_LEAVE
        self.manager_b.save(update_fields=['employment_status'])
        self.teamlead_b.employment_status = TeamLead.teamStatus.TERMINATED
        self.teamlead_b.save(update_fields=['employment_status'])
        client = self.client_for(self.admin_a)

        managers = self.rows(client, '/api/v1/staff/managers/?active=true')
        team_leads = self.rows(client, '/api/v1/staff/team-leads/?active=true')
        self.assertEqual({row['code'] for row in managers}, {self.manager_a.code})
        self.assertEqual({row['code'] for row in team_leads}, {self.teamlead_a.code})

    def test_customer_assignment_changes_are_recorded(self):
        client = self.client_for(self.admin_a)
        created = client.post(
            "/api/v1/customers/",
            {
                "customer_type": "INDIVIDUAL",
                "full_name": "Assigned Customer",
                "primary_phone": "9000000099",
                "preferred_channel": "phone",
                "assigned_to": str(self.employee_a1.id),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        customer_id = created.data["id"]

        updated = client.patch(
            f"/api/v1/customers/{customer_id}/",
            {"assigned_to": str(self.employee_a2.id), "change_reason": "Team workload balance"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        history = client.get(f"/api/v1/customers/{customer_id}/history/")
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(CustomerAssignmentHistory.objects.filter(customer_id=customer_id).count(), 2)
        entries = {(row["previous_owner_name"], row["new_owner_name"], row["reason"]) for row in history.data}
        self.assertIn((None, "northwind_employee_1", "Initial customer assignment"), entries)
        self.assertIn(("northwind_employee_1", "northwind_employee_2", "Team workload balance"), entries)

    def test_conversation_endpoints_are_removed_and_message_drafts_remain_scoped(self):
        employee_client = self.client_for(self.employee_a1.user)
        self.assertEqual(employee_client.get("/api/v1/communications/interactions/").status_code, 404)
        self.assertEqual(employee_client.get("/api/v1/communications/attendees/").status_code, 404)
        draft = employee_client.post(
            "/api/v1/communications/drafts/",
            {"customer": str(self.customer_b.id), "channel": "EMAIL", "message": "Private draft"},
            format="json",
        )
        self.assertEqual(draft.status_code, 400, draft.data)

    def test_staff_creation_is_limited_and_independent_lead_creation_is_disabled(self):
        admin_a = self.client_for(self.admin_a)
        admin_b = self.client_for(self.admin_b)

        onboard = admin_a.post(
            "/api/v1/staff/onboard/",
            {
                "staff_type": "team_lead",
                "username": "northwind_added_teamlead",
                "email": "northwind_added_teamlead@example.test",
                "password": "test-password",
                "code": "NW-TL-NEW",
                "department_id": str(self.department_a.id),
                "reporting_manager_id": str(self.manager_a.id),
            },
            format="json",
        )
        self.assertEqual(onboard.status_code, 201, onboard.data)
        new_teamlead = TeamLead.objects.get(code="NW-TL-NEW")
        self.assertEqual(new_teamlead.organization, self.org_a)
        self.assertEqual(new_teamlead.user.default_organization, self.org_a)

        cross_org_onboard = admin_a.post(
            "/api/v1/staff/onboard/",
            {
                "staff_type": "team_lead",
                "username": "wrong_org_teamlead",
                "email": "wrong_org_teamlead@example.test",
                "password": "test-password",
                "code": "WRONG-ORG-TL",
                "department_id": str(self.department_c.id),
            },
            format="json",
        )
        self.assertEqual(cross_org_onboard.status_code, 400, cross_org_onboard.data)
        self.assertFalse(get_user_model().objects.filter(username="wrong_org_teamlead").exists())

        at_staff_cap = admin_a.post(
            "/api/v1/staff/onboard/",
            {
                "staff_type": "team_lead",
                "username": "northwind_over_cap_teamlead",
                "email": "northwind_over_cap_teamlead@example.test",
                "password": "test-password",
                "code": "NW-TL-OVER-CAP",
                "department_id": str(self.department_a.id),
            },
            format="json",
        )
        self.assertEqual(at_staff_cap.status_code, 400, at_staff_cap.data)
        self.assertFalse(get_user_model().objects.filter(username="northwind_over_cap_teamlead").exists())

        contoso_teamlead = admin_b.post(
            "/api/v1/staff/onboard/",
            {
                "staff_type": "team_lead",
                "username": "contoso_added_teamlead",
                "email": "contoso_added_teamlead@example.test",
                "password": "test-password",
                "code": "CO-TL-NEW",
                "department_id": str(self.department_c.id),
                "reporting_manager_id": str(self.manager_c.id),
            },
            format="json",
        )
        self.assertEqual(contoso_teamlead.status_code, 201, contoso_teamlead.data)
        self.assertEqual(TeamLead.objects.get(code="CO-TL-NEW").organization, self.org_b)

        # Qualified applications are the only supported lead source.
        lead_count = Lead.objects.count()
        rejected_lead = admin_a.post(
            "/api/v1/leads/",
            {
                "contact_name": "Over-limit Northwind Lead",
                "phone": "9000000001",
                "assigned_to": str(self.employee_a1.id),
            },
            format="json",
        )
        self.assertEqual(rejected_lead.status_code, 405, rejected_lead.data)

        accepted_lead = admin_b.post(
            "/api/v1/leads/",
            {
                "contact_name": "Contoso New Lead",
                "phone": "9000000002",
                "assigned_to": str(self.employee_c.id),
                "state": "Gujarat",
            },
            format="json",
        )
        self.assertEqual(accepted_lead.status_code, 405, accepted_lead.data)
        self.assertEqual(Lead.objects.count(), lead_count)

    def test_current_organization_update_cannot_deactivate_its_tenant(self):
        response = self.client_for(self.admin_a).patch(
            '/api/v1/organizations/current/',
            {'name': 'Northwind Updated', 'is_active': False},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.name, 'Northwind Updated')
        self.assertTrue(self.org_a.is_active)

    def test_team_leader_must_belong_to_the_selected_department(self):
        response = self.client_for(self.admin_a).patch(
            f'/api/v1/organizations/teams/{self.team_a.id}/',
            {'team_leader': str(self.employee_b.id)},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('team_leader', response.data)

    def test_datetime_date_range_uses_the_organization_timezone(self):
        self.org_a.timezone = 'Asia/Kolkata'
        self.org_a.save(update_fields=['timezone'])
        before_local_day = self.make_task(self.org_a, self.employee_a1, 'before local day')
        inside_local_day = self.make_task(self.org_a, self.employee_a1, 'inside local day')
        after_local_day = self.make_task(self.org_a, self.employee_a1, 'after local day')
        Task.objects.filter(pk=before_local_day.pk).update(
            created_at=datetime(2026, 1, 1, 18, 29, 59, tzinfo=datetime_timezone.utc),
        )
        Task.objects.filter(pk=inside_local_day.pk).update(
            created_at=datetime(2026, 1, 2, 18, 29, 59, tzinfo=datetime_timezone.utc),
        )
        Task.objects.filter(pk=after_local_day.pk).update(
            created_at=datetime(2026, 1, 2, 18, 30, 0, tzinfo=datetime_timezone.utc),
        )
        request = SimpleNamespace(
            user=self.admin_a,
            headers={},
            query_params={'start_date': '2026-01-02', 'end_date': '2026-01-02'},
        )

        filtered = apply_date_range(Task.objects.filter(organization=self.org_a), request, 'created_at')

        self.assertEqual(list(filtered.values_list('pk', flat=True)), [inside_local_day.pk])
