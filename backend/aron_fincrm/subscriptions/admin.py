from django.contrib import admin, messages

from subscriptions.enterprise_workflow import (
    EnterpriseWorkflowError,
    initiate_enterprise_checkout,
    send_inquiry_notifications,
)
from .models import (
    EnterpriseInquiry,
    Payment,
    Plan,
    PlanCheckout,
    Subscription,
)


@admin.register(EnterpriseInquiry)
class EnterpriseInquiryAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'email', 'organization_name', 'status', 'created_at',
        'customer_email_sent', 'admin_email_sent', 'payment_link_email_sent_at',
    )
    list_filter = ('status', 'created_at', 'customer_email_sent', 'admin_email_sent')
    search_fields = ('full_name', 'email', 'organization_name')
    readonly_fields = (
        'id', 'idempotency_key', 'created_at', 'customer_email_sent',
        'admin_email_sent', 'payment_link_email_sent_at',
    )
    actions = ('send_missing_notifications', 'initiate_payment_workflow')
    fieldsets = (
        ('Inquiry', {'fields': (
            'id', 'full_name', 'email', 'phone', 'organization_name',
            'organization', 'website', 'linkedin_url', 'note', 'created_at',
        )}),
        ('Review', {'fields': (
            'status', 'internal_notes', 'agreed_amount', 'billing_cycle',
            'assigned_admin', 'custom_plan',
        )}),
        ('Notifications and checkout', {'fields': (
            'idempotency_key', 'customer_email_sent', 'admin_email_sent',
            'payment_link_email_sent_at',
        )}),
    )

    @admin.action(description='Retry missing inquiry notification emails')
    def send_missing_notifications(self, request, queryset):
        for inquiry in queryset:
            complete = send_inquiry_notifications(inquiry, only_unsent=True)
            self.message_user(
                request,
                f'{inquiry.email}: ' + ('all notifications sent.' if complete else 'one or more notifications remain pending.'),
                level=messages.SUCCESS if complete else messages.WARNING,
            )

    @admin.action(description='Create and email the approved Enterprise payment checkout')
    def initiate_payment_workflow(self, request, queryset):
        for inquiry in queryset:
            try:
                initiate_enterprise_checkout(inquiry.pk)
            except EnterpriseWorkflowError as error:
                self.message_user(request, f'{inquiry.email}: {error}', level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    f'{inquiry.email}: negotiated checkout created and emailed.',
                    level=messages.SUCCESS,
                )


admin.site.register(Plan)
admin.site.register(Subscription)
admin.site.register(Payment)
admin.site.register(PlanCheckout)
