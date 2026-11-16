import uuid

from django.db import models


class Interaction(models.Model):
    class InteractionType(models.TextChoices):
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        EMAIL = "EMAIL", "Email"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        NOTE = "NOTE", "Note"

    class Direction(models.TextChoices):
        INBOUND = "INBOUND", "Inbound"
        OUTBOUND = "OUTBOUND", "Outbound"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
    )
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
    )
    application = models.ForeignKey(
        "applications.FinancialApplication",
        on_delete=models.SET_NULL,
        null=True,
    )
    
    employee = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
    )
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    subject = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=50, blank=True)
    occurred_at = models.DateTimeField()
    next_action = models.TextField(blank=True)
    external_reference = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communications_interaction"


class InteractionAttendee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interaction = models.ForeignKey(
        "communications.Interaction",
        on_delete=models.CASCADE,
    )
    employee = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
    )
    external_name = models.CharField(max_length=200, blank=True)
    external_email = models.EmailField(blank=True)

    class Meta:
        db_table = "communications_interactionattendee"


class MessageDraft(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
    )
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communications_messagedraft"
