from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from django.db.models import Q
from permitions.models import Role, Permission
from permitions.serializers import RoleSerializer, PermissionSerializer
from organizations.tenant import get_user_organization
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin


class RoleViewSet(viewsets.ModelViewSet):
    """
    CRUD for Roles:
    GET: Lists system roles + organization custom roles.
    POST, PATCH, DELETE: Org Admin only for creating/editing custom roles.
    """
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticatedTenant]

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user)
        if not org:
            return Role.objects.filter(is_system_role=True)
        return Role.objects.filter(Q(is_system_role=True) | Q(organization=org)).order_by('-is_system_role', 'name')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedTenant(), IsOrgAdmin()]
        return [IsAuthenticatedTenant()]

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system_role:
            return Response(
                {"detail": "System roles cannot be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class PermissionListView(generics.ListAPIView):
    """
    GET /api/v1/permissions/
    Lists all available system module permissions for role construction.
    """
    queryset = Permission.objects.all().order_by('module', 'action')
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticatedTenant]
    pagination_class = None
