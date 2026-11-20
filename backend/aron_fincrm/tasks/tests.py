from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from employes.models import Employee
from organizations.models import Organization
from tasks.models import Task


class TaskDateValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.organization = Organization.objects.create(name='Task dates', slug='task-dates')
        self.user = User.objects.create_user(
            username='task_date_employee', password='test-password',
            default_organization=self.organization,
        )
        self.employee = Employee.objects.create(
            organization=self.organization,
            user=self.user,
            employee_code='TASK-DATE-EMP',
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_task(self, due_date):
        return self.client.post(
            '/api/v1/tasks/',
            {
                'title': 'Call customer',
                'assigned_to_user': str(self.user.id),
                'due_date': due_date,
            },
            format='json',
        )

    def test_new_task_rejects_past_day_but_allows_today(self):
        local_zone = ZoneInfo(self.organization.timezone)
        today = timezone.now().astimezone(local_zone).date()
        yesterday_at_noon = datetime.combine(today - timedelta(days=1), time(12)).isoformat()

        past = self.create_task(yesterday_at_noon)
        self.assertEqual(past.status_code, 400, past.data)
        self.assertIn('due_date', past.data)
        self.assertEqual(Task.objects.count(), 0)

        today_at_start = datetime.combine(today, time.min).isoformat()
        same_day = self.create_task(today_at_start)
        self.assertEqual(same_day.status_code, 201, same_day.data)
        self.assertEqual(Task.objects.count(), 1)

    def test_task_can_be_reassigned_using_the_recipient_field(self):
        User = get_user_model()
        replacement_user = User.objects.create_user(
            username='replacement_employee', password='test-password',
            default_organization=self.organization,
        )
        replacement_employee = Employee.objects.create(
            organization=self.organization,
            user=replacement_user,
            employee_code='TASK-DATE-EMP-2',
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        admin = User.objects.create_user(
            username='task_admin', password='test-password',
            default_organization=self.organization,
        )
        admin_client = APIClient()
        admin_client.force_authenticate(admin)
        created = admin_client.post(
            '/api/v1/tasks/',
            {
                'title': 'Review customer file',
                'assigned_to_user': str(self.user.id),
                'due_date': (timezone.now() + timedelta(days=2)).isoformat(),
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)

        updated = admin_client.patch(
            f"/api/v1/tasks/{created.data['id']}/",
            {'assigned_to_user': str(replacement_user.id)},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        task = Task.objects.get(pk=created.data['id'])
        self.assertEqual(task.assigned_to_id, replacement_employee.id)
        self.assertEqual(task.assigned_to_user_id, replacement_user.id)
