from django.contrib import admin
from .models import (
    Department,
    Team,
    organizations_organization,
)

admin.site.register(organizations_organization)
admin.site.register(Department)
admin.site.register(Team)