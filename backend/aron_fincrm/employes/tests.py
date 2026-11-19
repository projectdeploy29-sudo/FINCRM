from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from organizations.models import organizations_organization, Department, Team
from accounts.models import Manager, TeamLead
from employes.models import Employee, EmployeeAssignmentHistory
from permitions.models import Role
from subscriptions.models import Plan, Subscription

User = get_user_model()


class Stage2HierarchyAndStaffTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        call_command('seed_roles_permissions')
        call_command('seed_plans')

        # 1. Create Organization & Org Admin
        self.org = organizations_organization.objects.create(
            name="Quantum Finance",
            slug="quantum-finance",
            currency="INR"
        )
        self.admin_user = User.objects.create_user(
            username="quantum_admin",
            email="admin@quantum.com",
            password="AdminPassword123",
            default_organization=self.org,
            is_staff=True
        )

        # Obtain token for Org Admin
        login_res = self.client.post(
            reverse('auth_login'),
            {"username": "quantum_admin", "password": "AdminPassword123"}
        )
        self.admin_token = login_res.json()['access']

    def test_department_and_team_lifecycle(self):
        """
        Verify that Departments and Teams can be created, listed, and queried.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')

        # 1. Create Department
        dept_res = self.client.post(
            reverse('department-list'),
            {"name": "Retail Loans", "description": "Personal and Home Loans"},
            format='json'
        )
        self.assertEqual(dept_res.status_code, status.HTTP_201_CREATED)
        dept_id = dept_res.json()['id']

        # 2. Create Team under Department
        team_res = self.client.post(
            reverse('team-list'),
            {"name": "Home Loan Express", "department": dept_id, "description": "Express processing team"},
            format='json'
        )
        self.assertEqual(team_res.status_code, status.HTTP_201_CREATED)
        team_id = team_res.json()['id']

        # 3. List Departments
        list_res = self.client.get(reverse('department-list'))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.json()['results']), 1)
        self.assertEqual(list_res.json()['results'][0]['teams_count'], 1)

    def test_staff_onboarding_and_hierarchy_scoping(self):
        """
        Verify:
        - Org Admin onboards a Manager
        - Manager onboards a Team Lead
        - Team Lead onboards an Employee
        - Updating Employee department/team creates an EmployeeAssignmentHistory audit log
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')

        # Step 1: Admin creates Department
        dept = Department.objects.create(organization=self.org, name="Credit Underwriting")

        # Step 2: Admin onboards a Manager
        mgr_res = self.client.post(
            reverse('staff_onboard'),
            {
                "staff_type": "manager",
                "username": "mgr_anil",
                "email": "anil@quantum.com",
                "password": "MgrPassword123",
                "first_name": "Anil",
                "last_name": "Kumar",
                "code": "MGR001",
                "designation": "General Manager - Credit",
            },
            format='json'
        )
        self.assertEqual(mgr_res.status_code, status.HTTP_201_CREATED)
        mgr_user = User.objects.get(username="mgr_anil")
        mgr_obj = Manager.objects.get(user=mgr_user)
        dept.manager = mgr_obj
        dept.save()

        # Step 3: Manager logs in and onboards Team Lead
        mgr_login = self.client.post(
            reverse('auth_login'),
            {"username": "mgr_anil", "password": "MgrPassword123"}
        )
        self.assertEqual(mgr_login.status_code, status.HTTP_200_OK)
        mgr_token = mgr_login.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {mgr_token}')

        tl_res = self.client.post(
            reverse('staff_onboard'),
            {
                "staff_type": "team_lead",
                "username": "tl_priya",
                "email": "priya@quantum.com",
                "password": "TlPassword123",
                "first_name": "Priya",
                "last_name": "Sharma",
                "code": "TL001",
                "department_id": str(dept.id),
                "reporting_manager_id": str(mgr_obj.id),
                "designation": "Team Lead - Mortgage",
            },
            format='json'
        )
        self.assertEqual(tl_res.status_code, status.HTTP_201_CREATED)
        tl_user = User.objects.get(username="tl_priya")
        tl_obj = TeamLead.objects.get(user=tl_user)

        # Create Team led by this Team Lead
        team = Team.objects.create(
            organization=self.org,
            department=dept,
            name="Mortgage Verification Team",
            team_lead=tl_obj
        )

        # Step 4: Team Lead logs in and onboards an Employee
        tl_login = self.client.post(
            reverse('auth_login'),
            {"username": "tl_priya", "password": "TlPassword123"}
        )
        tl_token = tl_login.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tl_token}')

        employee_role = Role.objects.get(code='general_employee')
        emp_res = self.client.post(
            reverse('staff_onboard'),
            {
                "staff_type": "employee",
                "username": "emp_rahul",
                "email": "rahul@quantum.com",
                "password": "EmpPassword123",
                "first_name": "Rahul",
                "last_name": "Verma",
                "code": "EMP001",
                "department_id": str(dept.id),
                "team_id": str(team.id),
                "role_id": str(employee_role.id),
                "designation": "Credit Analyst",
            },
            format='json'
        )
        self.assertEqual(emp_res.status_code, status.HTTP_201_CREATED)
        emp_id = emp_res.json()['profile']['id']

        # Verify initial assignment history
        emp_obj = Employee.objects.get(id=emp_id)
        history_qs = EmployeeAssignmentHistory.objects.filter(employee=emp_obj)
        self.assertEqual(history_qs.count(), 1)
        self.assertEqual(history_qs.first().reason, "Initial staff onboarding")

        # Step 5: Transfer employee to another team/dept and verify audit history
        new_dept = Department.objects.create(organization=self.org, name="Risk Assessment")
        patch_res = self.client.patch(
            reverse('staff_employee-detail', kwargs={'pk': emp_id}),
            {"department": str(new_dept.id), "change_reason": "Promoted to Risk Dept"},
            format='json'
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)

        # Verify history updated
        hist_res = self.client.get(reverse('staff_employee-history', kwargs={'pk': emp_id}))
        self.assertEqual(hist_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(hist_res.json()), 2)
        self.assertEqual(hist_res.json()[0]['reason'], "Promoted to Risk Dept")

    def test_hierarchy_tree_endpoint(self):
        """
        Verify GET /api/v1/hierarchy/tree/ returns the nested structure.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')
        dept = Department.objects.create(organization=self.org, name="Operations")
        team = Team.objects.create(organization=self.org, department=dept, name="Ops Alpha")

        res = self.client.get(reverse('hierarchy_tree_global'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['organization']['name'], "Quantum Finance")
        self.assertEqual(data['total_departments'], 1)
        self.assertEqual(data['total_teams'], 1)

    def test_subscriptions_and_tier_limits(self):
        """
        Verify subscribing to a plan and checking current subscription status.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')

        # 1. List Plans
        plans_res = self.client.get(reverse('subscription_plans'))
        self.assertEqual(plans_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(plans_res.json()), 3)

        growth_plan = Plan.objects.get(code='growth')

        # 2. Subscribe to Growth Plan
        sub_res = self.client.post(
            reverse('subscription_subscribe'),
            {
                "plan_id": str(growth_plan.id),
                "billing_cycle": "MONTHLY",
                "payment_provider": "RAZORPAY",
                "provider_payment_id": "pay_test_12345",
            },
            format='json'
        )
        self.assertEqual(sub_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sub_res.json()['status'], 'active')

        # 3. Check Current Subscription
        curr_res = self.client.get(reverse('subscription_current'))
        self.assertEqual(curr_res.status_code, status.HTTP_200_OK)
        curr_data = curr_res.json()
        self.assertTrue(curr_data['has_active_subscription'])
        self.assertEqual(curr_data['plan_details']['code'], 'growth')
        self.assertIn('usage', curr_data)
        self.assertEqual(curr_data['usage']['max_staff_allowed'], 200)
