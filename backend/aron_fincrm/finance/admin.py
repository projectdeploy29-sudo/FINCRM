from django.contrib import admin
from .models import *

admin.site.register(RepaymentSchedule)
admin.site.register(RepaymentHistory)

@admin.register(RepaymentPayment)
class RepaymentPaymentAdmin(admin.ModelAdmin):
    exclude = ('payment_proof',)
