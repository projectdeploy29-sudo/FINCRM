from django.urls import path
from subscriptions.views import (
    PlanListView,
    SubscriptionCurrentView,
    SubscribeView,
    CancelSubscriptionView,
    PaymentHistoryView,
)

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='subscription_plans'),
    path('current/', SubscriptionCurrentView.as_view(), name='subscription_current'),
    path('subscribe/', SubscribeView.as_view(), name='subscription_subscribe'),
    path('cancel/', CancelSubscriptionView.as_view(), name='subscription_cancel'),
    path('payments/', PaymentHistoryView.as_view(), name='subscription_payments'),
]
