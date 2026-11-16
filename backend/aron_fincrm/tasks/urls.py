from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tasks.views import TaskViewSet, CustomerFollowUpViewSet, LeadFollowUpViewSet, ApplicationFollowUpViewSet, followups_today, dashboard
router=DefaultRouter(); router.register('tasks',TaskViewSet,basename='task'); router.register('followups/customers',CustomerFollowUpViewSet,basename='customer-followup'); router.register('followups/leads',LeadFollowUpViewSet,basename='lead-followup'); router.register('followups/applications',ApplicationFollowUpViewSet,basename='application-followup')
urlpatterns=router.urls+[path('followups/today/',followups_today),path('dashboards/<str:role>/',dashboard)]
