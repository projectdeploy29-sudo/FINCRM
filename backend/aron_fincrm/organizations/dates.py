from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


def organization_timezone(request=None):
    """Return the active tenant timezone, falling back to Django's configured zone."""
    organization = None
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        from organizations.tenant import get_user_organization

        organization = get_user_organization(request.user, request)
    name = getattr(organization, 'timezone', None) or settings.TIME_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return timezone.get_default_timezone()


def organization_local_date(request=None):
    return timezone.now().astimezone(organization_timezone(request)).date()


class OrganizationDateTimeField(serializers.DateTimeField):
    """Interpret timezone-free form datetimes in the active organization's zone."""

    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else value
        if isinstance(parsed, datetime) and timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, organization_timezone(self.context.get('request')))
        return super().to_internal_value(parsed)
