from django.urls import path, include
from rest_framework.routers import DefaultRouter
from organizations.views import (
    OrganizationRegistrationView,
    CurrentOrganizationView,
    DepartmentViewSet,
    TeamViewSet,
    HierarchyTreeView,
)

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'teams', TeamViewSet, basename='team')

urlpatterns = [
    path('register/', OrganizationRegistrationView.as_view(), name='organization_register'),
    path('current/', CurrentOrganizationView.as_view(), name='organization_current'),
    path('hierarchy/tree/', HierarchyTreeView.as_view(), name='hierarchy_tree'),
    path('', include(router.urls)),
]

