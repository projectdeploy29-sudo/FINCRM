from django.contrib import admin
from .models import ApplicationStatusHistory, FinancialApplication

admin.site.register(FinancialApplication)
admin.site.register(ApplicationStatusHistory)
