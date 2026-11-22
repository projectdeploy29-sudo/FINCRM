from django.contrib import admin
from .models import Permission, Role, RolePermission


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 1
    autocomplete_fields = ['permission']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'organization', 'is_system_role', 'created_at')
    list_filter = ('is_system_role', 'organization')
    search_fields = ('name', 'code', 'description')
    inlines = [RolePermissionInline]


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('codename', 'module', 'action', 'description')
    list_filter = ('module', 'action')
    search_fields = ('codename', 'module', 'action', 'description')


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission')
    list_filter = ('role__name', 'permission__module')
    search_fields = ('role__name', 'permission__codename', 'permission__module')
