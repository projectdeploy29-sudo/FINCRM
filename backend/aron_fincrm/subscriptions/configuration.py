from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from subscriptions.models import SubscriptionPlatformSettings


def is_subscription_checkout_enabled():
    """Use the persisted platform control, falling back to env on unmigrated installs."""
    try:
        enabled = SubscriptionPlatformSettings.objects.filter(pk=1).values_list('checkout_enabled', flat=True).first()
    except (OperationalError, ProgrammingError):
        return bool(settings.SUBSCRIPTION_CHECKOUT_ENABLED)
    if enabled is None:
        return bool(settings.SUBSCRIPTION_CHECKOUT_ENABLED)
    return enabled
