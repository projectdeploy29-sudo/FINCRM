from django.contrib import admin
from .models import *

admin.site.register(RepaymentSchedule)
admin.site.register(RepaymentHistory)
admin.site.register(RepaymentPayment)