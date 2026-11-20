from django.db import connection
from django.utils import timezone
from rest_framework import serializers

from accounts.models import Manager, TeamLead
from employes.models import Employee
from leads.models import Lead
from subscriptions.models import Subscription


RESOURCE_LIMITS = {
    'employees': ('max_employees', 'staff'),
    'leads': ('max_leads', 'leads'),
}


def active_subscription(organization, *, lock=False):
    if not organization:
        return None
    subscriptions = Subscription.objects.filter(
        organization=organization,
        status__in=(Subscription.Status.ACTIVE, Subscription.Status.TRIALING),
        end_date__gt=timezone.now(),
    ).select_related('plan').order_by('-created_at')
    if lock and connection.features.has_select_for_update:
        subscriptions = subscriptions.select_for_update()
    return subscriptions.first()


def entitlement_value(organization, name):
    """Return a configured plan limit, or None when no active plan limits it."""
    subscription = active_subscription(organization)
    if not subscription or not subscription.plan:
        return None
    return getattr(subscription.plan, name, None)


def resource_usage(organization, resource):
    if resource == 'leads':
        return Lead.objects.filter(organization=organization).count()
    if resource == 'employees':
        return (
            Employee.objects.filter(organization=organization).count()
            + Manager.objects.filter(organization=organization).count()
            + TeamLead.objects.filter(organization=organization).count()
        )
    raise ValueError(f'Unknown subscription resource: {resource}')


def enforce_resource_limit(organization, resource, *, lock=False):
    if not organization:
        raise serializers.ValidationError({'organization': 'An organization is required.'})
    try:
        limit_field, label = RESOURCE_LIMITS[resource]
    except KeyError as error:
        raise ValueError(f'Unknown subscription resource: {resource}') from error
    subscription = active_subscription(organization, lock=lock)
    limit = getattr(subscription.plan, limit_field, None) if subscription and subscription.plan else None
    if limit is None:
        return
    current = resource_usage(organization, resource)
    if current >= limit:
        raise serializers.ValidationError({
            'subscription': f'This plan allows up to {limit} {label}. Upgrade your plan to add more.'
        })
