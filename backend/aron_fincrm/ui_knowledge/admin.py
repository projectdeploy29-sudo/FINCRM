from django.contrib import admin

from ui_knowledge.models import UIComponent, UIFeature, UINavigationItem, UIPage, UISyncRun


@admin.register(UIPage)
class UIPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'module_id', 'nav_label', 'minimum_role_level', 'is_active', 'last_synced_at')
    list_filter = ('is_active', 'minimum_role_level')
    search_fields = ('title', 'nav_label', 'source_path')


@admin.register(UIComponent)
class UIComponentAdmin(admin.ModelAdmin):
    list_display = ('name', 'component_type', 'source_path', 'is_active', 'last_synced_at')
    list_filter = ('component_type', 'is_active')
    search_fields = ('name', 'source_path')


@admin.register(UIFeature)
class UIFeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'page', 'component_type', 'minimum_role_level', 'is_verified', 'is_active')
    list_filter = ('component_type', 'is_verified', 'requires_verification', 'is_active')
    search_fields = ('name', 'page__title', 'purpose', 'location')
    readonly_fields = ('source_hash', 'documentation_version', 'last_synced_at')


@admin.register(UINavigationItem)
class UINavigationItemAdmin(admin.ModelAdmin):
    list_display = ('label', 'module_id', 'parent', 'minimum_role_level', 'is_active')
    list_filter = ('is_active', 'minimum_role_level')
    search_fields = ('label', 'module_id')


@admin.register(UISyncRun)
class UISyncRunAdmin(admin.ModelAdmin):
    list_display = ('started_at', 'status', 'full_sync', 'source_root', 'completed_at')
    list_filter = ('status', 'full_sync')
    readonly_fields = ('started_at', 'completed_at', 'counts', 'warning', 'error')
