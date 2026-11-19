from rest_framework.permissions import BasePermission
from organizations.tenant import get_user_organization, get_user_role_context


class IsAuthenticatedTenant(BasePermission):
    """
    Allows access only to authenticated users who belong to an active organization.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role_ctx = get_user_role_context(request.user, request)
        if role_ctx['role_code'] == 'lead_portal':
            allowed_path=request.path.startswith('/api/v1/leads/') or request.path.rstrip('/')=='/api/v1/auth/me'
            return request.method in ('GET', 'HEAD', 'OPTIONS') and allowed_path
        if request.user.is_superuser:
            return True
        org = get_user_organization(request.user)
        return org is not None and getattr(org, 'is_active', True)


class IsOrgAdmin(BasePermission):
    """
    Allows access only to Organization Admins or Superusers.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        role_ctx = get_user_role_context(request.user, request)
        return role_ctx['hierarchy_level'] >= 90


class IsManager(BasePermission):
    """
    Allows access to Managers, Org Admins, and Superusers.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        role_ctx = get_user_role_context(request.user, request)
        return role_ctx['hierarchy_level'] >= 70


class IsTeamLead(BasePermission):
    """
    Allows access to Team Leads, Managers, Org Admins, and Superusers.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        role_ctx = get_user_role_context(request.user, request)
        return role_ctx['hierarchy_level'] >= 50


class IsEmployee(BasePermission):
    """
    Allows access to Employees, Team Leads, Managers, Org Admins, and Superusers.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        role_ctx = get_user_role_context(request.user, request)
        return role_ctx['hierarchy_level'] >= 30


def has_permission_codename(user, codename):
    """
    Helper to check if a user has a specific permission codename.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role_ctx = get_user_role_context(user)
    if '*' in role_ctx['permissions']:
        return True
    return codename in role_ctx['permissions']
