from django.contrib import admin
from .models import ApplicationChecklist, ApplicationStatusHistory, FinancialApplication

admin.site.register(FinancialApplication)
admin.site.register(ApplicationStatusHistory)
admin.site.register(ApplicationChecklist)