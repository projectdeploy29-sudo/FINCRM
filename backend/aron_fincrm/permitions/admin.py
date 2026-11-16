from django.contrib import admin
from .models import Permission, Role, RolePermission

admin.site.register(Role)
admin.site.register(Permission)
admin.site.register(RolePermission)
