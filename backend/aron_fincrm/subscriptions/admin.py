from django.contrib import admin
from .models import (
    Payment,
    Plan,
    Subscription,
)

admin.site.register(Plan)
admin.site.register(Subscription)
admin.site.register(Payment)
