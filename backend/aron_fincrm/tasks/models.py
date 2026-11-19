import uuid

from django.db import models
from django.conf import settings
class Task(models.Model):

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="tasks"
    )

    title = models.CharField(max_length=255)

    description = models.TextField(blank=True, null=True)

    assigned_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    assigned_by_manager = models.ForeignKey(
        'accounts.Manager',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    assigned_by_teamlead = models.ForeignKey(
        'accounts.TeamLead',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    assigned_to = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
        null=True,
        blank=True,
    )
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_fincrm_tasks",
    )

    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks"
    )

    team = models.ForeignKey(
        "organizations.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks"
    )

    related_customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks"
    )

    related_lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks"
    )

    related_application = models.ForeignKey(
        "applications.FinancialApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks"
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    start_date = models.DateTimeField(
        null=True,
        blank=True
    )

    due_date = models.DateTimeField()

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class TaskHistory(models.Model):

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="history"
    )

    previous_status = models.CharField(
        max_length=20,
        choices=Task.Status.choices
    )

    new_status = models.CharField(
        max_length=20,
        choices=Task.Status.choices
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="task_status_changes"
    )

    comment = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task.title} - {self.new_status}"

class CostomerFollowUp(models.Model):

    class FollowUpType(models.TextChoices):
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        VISIT = "VISIT", "Visit"
        EMAIL = "EMAIL", "Email"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="costomer_followups"
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="followups",
    )

    assigned_to = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_customer_followups')
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_customer_followups')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    purpose = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_followups"
    )

    followup_type = models.CharField(
        max_length=20,
        choices=FollowUpType.choices
    )

    scheduled_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    outcome = models.TextField(
        blank=True,
        null=True
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    meeting_duration_minutes = models.PositiveSmallIntegerField(default=30)
    meeting_location = models.CharField(max_length=255, blank=True)
    meeting_url = models.URLField(blank=True)
    invitee_emails = models.TextField(blank=True, help_text="Comma-separated invitee email addresses")

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.followup_type} - {self.scheduled_at}"

class LeadFollowUp(models.Model):

    class FollowUpType(models.TextChoices):
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        VISIT = "VISIT", "Visit"
        EMAIL = "EMAIL", "Email"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="lead_followups"
    )

    lead = models.ForeignKey(
        "leads.lead",
        on_delete=models.CASCADE,
        related_name="followups",
    )

    assigned_to = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_lead_followups')
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_lead_followups')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    purpose = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        
    )

    followup_type = models.CharField(
        max_length=20,
        choices=FollowUpType.choices
    )

    scheduled_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    outcome = models.TextField(
        blank=True,
        null=True
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    meeting_duration_minutes = models.PositiveSmallIntegerField(default=30)
    meeting_location = models.CharField(max_length=255, blank=True)
    meeting_url = models.URLField(blank=True)
    invitee_emails = models.TextField(blank=True, help_text="Comma-separated invitee email addresses")

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.followup_type} - {self.scheduled_at}"

class applicationFollowUp(models.Model):

    class FollowUpType(models.TextChoices):
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        VISIT = "VISIT", "Visit"
        EMAIL = "EMAIL", "Email"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="application_followups"
    )

    application = models.ForeignKey(
        "applications.FinancialApplication",
        on_delete=models.CASCADE,
        related_name="followups",
    )

    assigned_to = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_application_followups')
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_application_followups')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    purpose = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        
    )

    followup_type = models.CharField(
        max_length=20,
        choices=FollowUpType.choices
    )

    scheduled_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    outcome = models.TextField(
        blank=True,
        null=True
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    meeting_duration_minutes = models.PositiveSmallIntegerField(default=30)
    meeting_location = models.CharField(max_length=255, blank=True)
    meeting_url = models.URLField(blank=True)
    invitee_emails = models.TextField(blank=True, help_text="Comma-separated invitee email addresses")

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.followup_type} - {self.scheduled_at}"


# Aliases for consistent naming
CustomerFollowUp = CostomerFollowUp
ApplicationFollowUp = applicationFollowUp