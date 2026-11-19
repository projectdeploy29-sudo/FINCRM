import uuid

from django.db import models


class Lead(models.Model):
    class Source(models.TextChoices):
        WEBSITE = "website", "Website"
        REFERRAL = "referral", "Referral"
        SOCIAL_MEDIA = "social_media", "Social media"
        CAMPAIGN = "campaign", "Campaign"
        COLD_CALL = "cold_call", "Cold call"
        WALK_IN = "walk_in", "Walk-in"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        UNQUALIFIED = "unqualified", "Unqualified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    lead_code = models.CharField(max_length=50)
    contact_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    assigned_to = models.ForeignKey(
        'employes.Employee',
        on_delete=models.PROTECT,
        related_name='assigned_leads',
        null=True,
        blank=True,
    )
    assigned_doc_officer = models.ForeignKey(
        'employes.Employee', on_delete=models.PROTECT, null=True, blank=True,
        related_name='assigned_document_leads',
    )
    assigned_sales_analyst = models.ForeignKey(
        'employes.Employee', on_delete=models.PROTECT, null=True, blank=True,
        related_name='assigned_sales_leads',
    )
    portal_user = models.OneToOneField(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lead_portal_profile',
    )
    converted_customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='converted_from_leads',
    )
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.PROTECT, null=True, blank=True,
        related_name='leads',
    )
    application = models.OneToOneField(
        'applications.FinancialApplication', on_delete=models.PROTECT, null=True, blank=True,
        related_name='lead_record',
    )

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    expected_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=3, default="INR")
    created_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        null=True,
        related_name='created_leads'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "leads_lead"




class LeadAssignmentHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey("leads.Lead", on_delete=models.CASCADE)
    old_owner = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="previous_lead_assignments",
    )
    new_owner = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="new_lead_assignments",
    )
    old_doc_officer = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_document_lead_assignments')
    new_doc_officer = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='new_document_lead_assignments')
    old_sales_analyst = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_sales_lead_assignments')
    new_sales_analyst = models.ForeignKey('employes.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='new_sales_lead_assignments')
    assigned_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "leads_leadassignmenthistory"


class LeadStatusHistory(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    lead=models.ForeignKey('leads.Lead',on_delete=models.CASCADE,related_name='status_history')
    old_status=models.CharField(max_length=20,blank=True,choices=Lead.Status.choices)
    new_status=models.CharField(max_length=20,choices=Lead.Status.choices)
    changed_by=models.ForeignKey('accounts.User',on_delete=models.PROTECT)
    notes=models.TextField(blank=True)
    changed_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table='leads_leadstatushistory'
        ordering=['-changed_at']

