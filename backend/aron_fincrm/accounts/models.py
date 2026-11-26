import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class PasswordResetRequest(models.Model):
    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE, related_name='password_reset_request')
    created_at = models.DateTimeField(default=timezone.now)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    default_organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.SET_NULL,
        null=True,
    )
    # subscription=models.OneToOneField('subscriptions.subscription',on_delete=models.CASCADE,null=True)

    class Meta:
        db_table = "accounts_user"


class Manager(models.Model):
    class ManagerStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    code = models.CharField(max_length=50)
    work_email = models.EmailField(blank=True)
    work_phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    join_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=ManagerStatus.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employees_manager"


class TeamLead(models.Model):
    class teamStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="teamlead_profiles",
    )
    code = models.CharField(max_length=50)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
    )

    manager = models.ForeignKey(
        "accounts.Manager",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    work_email = models.EmailField(blank=True)
    work_phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    join_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=teamStatus.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employees_Teamlead"


# Backward compatibility alias
Teamlead = TeamLead
