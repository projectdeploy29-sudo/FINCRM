import uuid

from django.conf import settings
from django.db import models


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default='INR')
    monthly_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    yearly_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    prices_confirmed = models.BooleanField(default=False)
    max_employees = models.PositiveIntegerField(default=10, null=True, blank=True)
    max_leads = models.PositiveIntegerField(default=500, null=True, blank=True)
    # Kept to match the applied 0004 migration and preserve existing plan data.
    daily_ai_tokens = models.PositiveIntegerField(default=10000, null=True, blank=True)
    features = models.JSONField(default=dict, blank=True)
    razorpay_plan_id = models.CharField(max_length=100, blank=True, db_index=True)
    storage_limit_mb = models.PositiveBigIntegerField(null=True, blank=True)
    included_services = models.JSONField(default=list, blank=True)
    additional_services = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    subscription_total_count = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plan"


class SubscriptionPlatformSettings(models.Model):
    """Persisted platform-wide subscription controls managed by FinCRM superusers."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    checkout_enabled = models.BooleanField(default=False)
    invoice_issuer_name = models.CharField(max_length=255, blank=True, default='')
    invoice_issuer_address = models.TextField(blank=True, default='')
    invoice_issuer_gstin = models.CharField(max_length=20, blank=True, default='')
    invoice_sac_hsn_code = models.CharField(max_length=30, blank=True, default='')
    invoice_gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_subscription_platform_settings',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_platformsettings'


class AIAssistantUsage(models.Model):
    """Provider-reported token usage for one successful AI assistant response."""
    organization = models.ForeignKey(
        'organizations.organizations_organization', on_delete=models.CASCADE,
        related_name='ai_assistant_usage',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_assistant_usage',
    )
    model_name = models.CharField(max_length=150, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'subscriptions_aiassistantusage'
        ordering = ['-created_at']



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
        null=True,
        blank=True,
        related_name='payments'
    )
    checkout = models.ForeignKey(
        "subscriptions.PlanCheckout",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    provider = models.CharField(max_length=100)
    provider_payment_id = models.CharField(max_length=255, blank=True)
    invoice_reference = models.CharField(max_length=150, blank=True)
    invoice_customer_gstin = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_payment"
        constraints = [
            models.UniqueConstraint(
                fields=['provider_payment_id'],
                condition=~models.Q(provider_payment_id=''),
                name='uniq_payment_provider_id_nonblank',
            ),
        ]


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
        HALTED = "halted", "Halted"

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
    razorpay_subscription_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
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
        PENDING_AUTHORIZATION = "pending_authorization", "Awaiting subscription authorization"

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
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATING)
    razorpay_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    registration_token_hash = models.CharField(max_length=64, blank=True)
    registration_token_expires_at = models.DateTimeField(null=True, blank=True)
    registration_token_used_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    registration_email_sent_at = models.DateTimeField(null=True, blank=True)
    enterprise_inquiry = models.OneToOneField(
        "subscriptions.EnterpriseInquiry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="checkout",
    )
    enterprise_access_token_hash = models.CharField(max_length=64, blank=True)
    enterprise_access_token_expires_at = models.DateTimeField(null=True, blank=True)
    payment_mode = models.CharField(max_length=12, choices=(('one_time', 'One time'), ('recurring', 'Recurring')), default='one_time')
    duration_count = models.PositiveIntegerField(default=1)
    razorpay_subscription_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    plan_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_plancheckout"


class EnterpriseInquiry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_REVIEW = "in_review", "In review"
        AGREED = "agreed", "Agreement reached"
        PAYMENT_INITIATED = "payment_initiated", "Payment initiated"
        CONVERTED = "converted", "Converted"
        CLOSED = "closed", "Closed"
        PENDING = "pending", "Pending"
        CONTACTED = "contacted", "Contacted"
        UNDER_DISCUSSION = "under_discussion", "Under discussion"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PLAN_CREATED = "plan_created", "Plan created"
        PAYMENT_PENDING = "payment_pending", "Payment pending"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enterprise_inquiries",
    )
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    organization_name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    internal_notes = models.TextField(blank=True)
    agreed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    billing_cycle = models.CharField(
        max_length=10,
        choices=Subscription.BillingCycle.choices,
        null=True,
        blank=True,
    )
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    payment_link_email_sent_at = models.DateTimeField(null=True, blank=True)
    assigned_admin = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_enterprise_inquiries',
    )
    custom_plan = models.ForeignKey(
        'subscriptions.Plan', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='enterprise_inquiries',
    )
    customer_email_sent = models.BooleanField(default=False)
    admin_email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscriptions_enterpriseinquiry"
        ordering = ["-created_at"]


class RazorpayWebhookEvent(models.Model):
    """Durable inbox for Razorpay's at-least-once webhook delivery."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload_sha256 = models.CharField(max_length=64)
    processed_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = 'subscriptions_razorpaywebhookevent'
