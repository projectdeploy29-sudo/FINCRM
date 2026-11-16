import uuid

from django.db import models


class Employee(models.Model):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE)
    employee_code = models.CharField(max_length=50)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
    )
    team = models.ForeignKey(
        "organizations.Team",
        on_delete=models.SET_NULL,
        null=True,
    )
    role=models.ForeignKey(
        "permitions.Role",
        on_delete=models.SET_NULL,
        null=True
    )
    additional_roles = models.ManyToManyField(
        "permitions.Role",
        blank=True,
        related_name="employees_with_additional_role",
    )
    manager = models.ForeignKey(
        "self",
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
        choices=EmploymentStatus.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employees_employee"



class EmployeeAssignmentHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey("employes.Employee", on_delete=models.CASCADE)
    previous_department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_employee_assignments",
    )
    new_department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_employee_assignments",
    )
    previous_team = models.ForeignKey(
        "organizations.Team",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_employee_assignments",
    )
    new_team = models.ForeignKey(
        "organizations.Team",
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_employee_assignments",
    )
    previous_role = models.ForeignKey(
        "permitions.Role",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_employee_assignments",
    )
    new_role = models.ForeignKey(
        "permitions.Role",
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_employee_assignments",
    )
    previous_manager = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_employee_assignments",
    )
    new_manager = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_employee_assignments",
    )

    changed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "employees_employeeassignmenthistory"
