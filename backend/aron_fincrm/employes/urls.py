from django.urls import path, include
from rest_framework.routers import DefaultRouter
from employes.views import (
    StaffOnboardingView,
    EmployeeViewSet,
    ManagerViewSet,
    TeamLeadViewSet,
)

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='staff_employee')
router.register(r'managers', ManagerViewSet, basename='staff_manager')
router.register(r'team-leads', TeamLeadViewSet, basename='staff_teamlead')

urlpatterns = [
    path('onboard/', StaffOnboardingView.as_view(), name='staff_onboard'),
    path('', include(router.urls)),
]
