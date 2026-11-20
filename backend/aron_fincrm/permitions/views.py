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
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'created_at']

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user)
        if not org:
            qs=Role.objects.filter(is_system_role=True)
        else:
            qs=Role.objects.filter(Q(is_system_role=True) | Q(organization=org))
        if self.request.query_params.get('employee_scope') == 'true':
            qs=qs.exclude(code__in={'super_admin','org_admin','manager','team_lead','lead_portal'})
        qs=qs.order_by('-is_system_role', 'name')
        return qs

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
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticatedTenant]
    pagination_class = None

    def get_queryset(self):
        return Permission.objects.exclude(module='documents').order_by('module', 'action')
