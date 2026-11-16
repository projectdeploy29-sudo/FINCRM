from django.contrib import admin
from .models import Lead, LeadAssignmentHistory

admin.site.register(Lead)

admin.site.register(LeadAssignmentHistory)
