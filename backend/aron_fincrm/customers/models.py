import uuid

from django.db import models


class Customer(models.Model):
    class CustomerType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        BUSINESS = "BUSINESS", "Business"

    class PreferredChannel(models.TextChoices):
        PHONE = "phone", "Phone"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        UNDER_REVIEW = "under_review", "Under review"
        CONVERTED = "converted", "Converted to lead"
        INACTIVE = "inactive", "Inactive"

    class Priority(models.TextChoices):
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    customer_code = models.CharField(max_length=50)
    customer_type = models.CharField(max_length=10, choices=CustomerType.choices)
    full_name = models.CharField(max_length=200, blank=True)
    legal_name = models.CharField(max_length=255, blank=True)
    primary_phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    alternate_phone = models.CharField(max_length=20, blank=True)
    preferred_channel = models.CharField(
        max_length=20,
        choices=PreferredChannel.choices,
    )
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pin_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default="India")
    business_category = models.CharField(max_length=100, blank=True)
    segment = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    # Customer conversion likelihood; distinct from VIP/General tags.
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "employes.employee",
        on_delete=models.SET_NULL,
        null=True,
    )
    assigned_to = models.ForeignKey(
        'employes.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_customers',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "customers_customer"




class CustomerTag(models.Model):
    class Tag(models.TextChoices):
        VIP = "VIP", "VIP"
        IMPORTANT = "importent", "Important"
        GENERAL = "General", "General"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        on_delete=models.CASCADE,
        db_column="costomer_id",
        related_name="tags",
    )
    tag = models.CharField(max_length=100, null=True, choices=Tag.choices)

    @property
    def costomer(self):
        return self.customer

    class Meta:
        db_table = "customers_customertag"


class CustomerAssignmentHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.CASCADE,
        related_name='assignment_history',
    )
    previous_owner = models.ForeignKey(
        'employes.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='previous_customer_assignments',
    )
    new_owner = models.ForeignKey(
        'employes.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='new_customer_assignments',
    )
    changed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customers_customerassignmenthistory'
        ordering = ['-changed_at']


class CustomerStatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20, blank=True, choices=Customer.Status.choices)
    new_status = models.CharField(max_length=20, choices=Customer.Status.choices)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']


