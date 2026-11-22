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


class PlanCheckout(models.Model):
    class Status(models.TextChoices):
        CREATING = "creating", "Creating Razorpay order"
        PENDING = "pending", "Awaiting payment"
        PROCESSING = "processing", "Payment verification in progress"
        PAID = "paid", "Paid; registration pending"
        ACTIVATED = "activated", "Subscription activated"
        COMPLETED = "completed", "Registration completed"
        FAILED = "failed", "Order creation failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey("subscriptions.Plan", on_delete=models.PROTECT, related_name="checkouts")
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_checkouts",
    )
    billing_cycle = models.CharField(max_length=10, choices=Subscription.BillingCycle.choices)
    purchaser_email = models.EmailField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATING)
    razorpay_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    registration_token_hash = models.CharField(max_length=64, blank=True)
    registration_token_expires_at = models.DateTimeField(null=True, blank=True)
    registration_token_used_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    registration_email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plancheckout"


class EnterpriseInquiry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    organization_name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    note = models.TextField(blank=True)
    customer_email_sent = models.BooleanField(default=False)
    admin_email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_enterpriseinquiry"
        ordering = ["-created_at"]
