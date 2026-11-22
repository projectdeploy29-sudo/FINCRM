from django.contrib import admin
from .models import (
    Payment,
    Plan,
    Subscription,
    PlanCheckout,
    EnterpriseInquiry,
)

admin.site.register(Plan)
admin.site.register(Subscription)
admin.site.register(Payment)
admin.site.register(PlanCheckout)
admin.site.register(EnterpriseInquiry)
