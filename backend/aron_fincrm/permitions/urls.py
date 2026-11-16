from django.urls import path, include
from rest_framework.routers import DefaultRouter
from permitions.views import RoleViewSet, PermissionListView

router = DefaultRouter()
router.register(r'roles', RoleViewSet, basename='role')

urlpatterns = [
    path('permissions/', PermissionListView.as_view(), name='permission_list'),
    path('', include(router.urls)),
]
