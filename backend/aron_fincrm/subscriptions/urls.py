from django.urls import path
from subscriptions.views import (
    PlanListView,
    SubscriptionCurrentView,
    SubscribeView,
    CancelSubscriptionView,
    PaymentHistoryView,
    PlanCheckoutCreateView,
    PlanCheckoutVerifyView,
    EnterpriseInquiryView,
)

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='subscription_plans'),
    path('checkout/create/', PlanCheckoutCreateView.as_view(), name='subscription_checkout_create'),
    path('checkout/verify/', PlanCheckoutVerifyView.as_view(), name='subscription_checkout_verify'),
    path('enterprise-inquiry/', EnterpriseInquiryView.as_view(), name='subscription_enterprise_inquiry'),
    path('current/', SubscriptionCurrentView.as_view(), name='subscription_current'),
    path('subscribe/', SubscribeView.as_view(), name='subscription_subscribe'),
    path('cancel/', CancelSubscriptionView.as_view(), name='subscription_cancel'),
    path('payments/', PaymentHistoryView.as_view(), name='subscription_payments'),
]
