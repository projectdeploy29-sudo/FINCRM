import uuid

from django.db import models


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    yearly_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_employees = models.PositiveIntegerField(default=10, null=True, blank=True)
    max_leads = models.PositiveIntegerField(default=500, null=True, blank=True)
    daily_ai_tokens = models.PositiveIntegerField(default=10000, null=True, blank=True)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plan"



class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    provider = models.CharField(max_length=100)
    provider_payment_id = models.CharField(max_length=255, blank=True)
    invoice_reference = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_payment"


class Subscription(models.Model):
    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        YEARLY = "YEARLY", "Yearly"

    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    plan = models.ForeignKey("subscriptions.Plan", on_delete=models.PROTECT)
    Subscriptioncode=models.CharField(unique=True,max_length=50)
    billing_cycle = models.CharField(max_length=10, choices=BillingCycle.choices)
    payment = models.ForeignKey(
        "subscriptions.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscription_records',
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    next_billing_date = models.DateField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_subscription"
