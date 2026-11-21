from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class WhatsAppMessageTemplate(models.Model):
    """Reusable message copy; a null organization marks a built-in template."""

    organization = models.ForeignKey(
        'organizations.organizations_organization',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='whatsapp_message_templates',
    )
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=1200)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'title', 'id']

    def __str__(self):
        return self.title


class WhatsAppMessage(models.Model):
    class FollowupKind(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        LEAD = 'lead', 'Lead'
        APPLICATION = 'application', 'Application'

    class Status(models.TextChoices):
        PREPARED = 'PREPARED', 'Prepared in WhatsApp'
        PENDING = 'PENDING', 'Pending'
        SENT = 'SENT', 'Accepted by WhatsApp'
        FAILED = 'FAILED', 'Failed'

    organization = models.ForeignKey(
        'organizations.organizations_organization',
        on_delete=models.CASCADE,
        related_name='whatsapp_messages',
    )
    followup_kind = models.CharField(max_length=20, choices=FollowupKind.choices)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64)
    followup = GenericForeignKey('content_type', 'object_id')
    recipient_name = models.CharField(max_length=200, blank=True)
    recipient_phone = models.CharField(max_length=32)
    message_body = models.TextField(max_length=4096)
    source_template = models.ForeignKey(
        WhatsAppMessageTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sent_messages',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREPARED)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error_detail = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='whatsapp_messages_sent',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['organization', 'followup_kind', 'object_id']),
            models.Index(fields=['organization', 'status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.followup_kind} WhatsApp to {self.recipient_phone} ({self.status})'
