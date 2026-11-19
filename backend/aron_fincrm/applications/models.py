import uuid

from django.db import models


class FinancialApplication(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        QUALIFIED = "qualified", "Qualified for lead conversion"
        UNQUALIFIED = "unqualified", "Unqualified"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DISBURSED = "disbursed", "Disbursed"
        COMPLETED = "completed", "Completed"
        WITHDRAWN = "withdrawn", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    application_code = models.CharField(max_length=50)
    application_type = models.CharField(max_length=100, blank=True)
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
    )
    
    assigned_employee = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    requested_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
    )
    financial_information = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    approved_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
    )
    disbursed_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
    )
    annual_interest_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    loan_tenure_months = models.PositiveIntegerField(null=True, blank=True)
    monthly_repayment_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    next_payment_due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    submitted_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "applications_financialapplication"


class ApplicationStatusHistory(models.Model):
    class Status(models.TextChoices):
            DRAFT = "draft", "Draft"
            SUBMITTED = "submitted", "Submitted"
            UNDER_REVIEW = "under_review", "Under review"
            QUALIFIED = "qualified", "Qualified for lead conversion"
            UNQUALIFIED = "unqualified", "Unqualified"
            APPROVED = "approved", "Approved"
            REJECTED = "rejected", "Rejected"
            DISBURSED = "disbursed", "Disbursed"
            COMPLETED = "completed", "Completed"
            WITHDRAWN = "withdrawn", "Withdrawn"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.FinancialApplication",
        on_delete=models.CASCADE,
    )
    old_status = models.CharField(max_length=50, blank=True,choices=Status.choices)
    new_status = models.CharField(max_length=50, choices=Status.choices)
    changed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "applications_applicationstatushistory"


class ApplicationChecklist(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.FinancialApplication",
        on_delete=models.CASCADE,
    )
    
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    remarks = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "applications_applicationchecklist"
