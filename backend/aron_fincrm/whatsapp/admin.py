from django.contrib import admin

from .models import WhatsAppMessage, WhatsAppMessageTemplate


@admin.register(WhatsAppMessageTemplate)
class WhatsAppMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('title', 'body')


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('recipient_name', 'recipient_phone', 'followup_kind', 'status', 'sent_by', 'created_at')
    list_filter = ('status', 'followup_kind', 'organization')
    search_fields = ('recipient_name', 'recipient_phone', 'message_body', 'provider_message_id')
    readonly_fields = tuple(field.name for field in WhatsAppMessage._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
