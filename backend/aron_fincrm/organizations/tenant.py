from django.db import models


def get_user_organization(user, request=None):
    """
    Returns the active organization for a given user.
    Supports request overrides (query param, request data, or header X-Organization-ID).
    For superusers without a default organization, falls back to the first active organization.
    """
    if not user or not user.is_authenticated:
        return None

    from organizations.models import organizations_organization

    # 1. Check request header or query param or body if provided
    if request:
        req_org_id = None
        if hasattr(request, 'headers') and request.headers.get('X-Organization-ID'):
            req_org_id = request.headers.get('X-Organization-ID')
        elif hasattr(request, 'query_params') and request.query_params.get('organization_id'):
            req_org_id = request.query_params.get('organization_id')
        elif hasattr(request, 'data') and isinstance(request.data, dict) and request.data.get('organization_id'):
            req_org_id = request.data.get('organization_id')

        if req_org_id:
            org = organizations_organization.objects.filter(id=req_org_id).first()
            if org:
                if user.is_superuser or user.default_organization_id == org.id:
                    return org

    # 2. Check default_organization on User
    if getattr(user, 'default_organization', None):
        return user.default_organization

    # 3. Check Manager profile
    manager = getattr(user, 'manager_set', None)
    if manager and manager.exists():
        return manager.first().organization

    # 4. Check TeamLead profile
    teamlead_profiles = getattr(user, 'teamlead_profiles', None)
    if teamlead_profiles and teamlead_profiles.exists():
        return teamlead_profiles.first().organization

    # 5. Check Employee profile
    employee = getattr(user, 'employee', None)

    if employee:
        return employee.organization

    # 6. Fallback for superuser / platform admin: bind to the first active organization
    if user.is_superuser:
        first_org = organizations_organization.objects.filter(is_active=True).first()
        if first_org:
            user.default_organization = first_org
            user.save(update_fields=['default_organization'])
            return first_org

    return None


def get_user_role_context(user, request=None):
    """
    Returns a dictionary detailing the user's role, hierarchy level,
    department, and team within their organization.
    """
    if not user or not user.is_authenticated:
        return {
            'role_code': 'anonymous',
            'role_name': 'Anonymous',
            'hierarchy_level': 0,
            'organization': None,
            'department': None,
            'team': None,
            'profile_id': None,
            'permissions': [],
        }

    org = get_user_organization(user, request)

    if user.is_superuser:
        return {
            'role_code': 'super_admin',
            'role_name': 'Super Administrator',
            'hierarchy_level': 100,
            'organization': org,
            'department': None,
            'team': None,
            'profile_id': str(user.id),
            'permissions': ['*'],
            'available_roles': [{'code': 'super_admin', 'name': 'Super Administrator', 'hierarchy_level': 100}],
        }


    # Check subordinate profiles
    manager_qs = getattr(user, 'manager_set', None)
    manager = manager_qs.first() if manager_qs and manager_qs.exists() else None

    teamlead_qs = getattr(user, 'teamlead_profiles', None)
    teamlead = teamlead_qs.first() if teamlead_qs and teamlead_qs.exists() else None

    employee = getattr(user, 'employee', None)

    # Lead portal accounts are deliberately distinct from organization administrators.
    lead_profile = getattr(user, 'lead_portal_profile', None)
    if lead_profile:
        return {
            'role_code': 'lead_portal', 'role_name': 'Lead Portal', 'hierarchy_level': 20,
            'organization': org, 'department': None, 'team': None,
            'profile_id': str(lead_profile.id), 'permissions': ['leads:portal_view'],
            'available_roles': [{'code': 'lead_portal', 'name': 'Lead Portal', 'hierarchy_level': 20}],
        }

    # 1. If user is Org Admin (has default_organization and no subordinate profile)
    if user.default_organization and not (manager or teamlead or employee):
        from permitions.models import RolePermission
        perms = list(RolePermission.objects.filter(role__code='org_admin').values_list('permission__codename', flat=True))
        if not perms:
            perms = ['*']
        return {
            'role_code': 'org_admin',
            'role_name': 'Organization Admin',
            'hierarchy_level': 90,
            'organization': org,
            'department': None,
            'team': None,
            'profile_id': str(user.id),
            'permissions': perms,
            'available_roles': [{'code': 'org_admin', 'name': 'Organization Admin', 'hierarchy_level': 90}],
        }

    # 2. Check Manager
    if manager:
        from permitions.models import RolePermission
        perms = list(RolePermission.objects.filter(role__code='manager').values_list('permission__codename', flat=True))
        managed_dept = manager.managed_departments.first() if hasattr(manager, 'managed_departments') else None
        return {
            'role_code': 'manager',
            'role_name': 'Manager',
            'hierarchy_level': 70,
            'organization': org,
            'department': managed_dept,
            'team': None,
            'profile_id': str(manager.id),
            'permissions': perms,
            'available_roles': [{'code': 'manager', 'name': 'Manager', 'hierarchy_level': 70}],
        }

    # 3. Check TeamLead
    if teamlead:
        from permitions.models import RolePermission
        perms = list(RolePermission.objects.filter(role__code='team_lead').values_list('permission__codename', flat=True))
        return {
            'role_code': 'team_lead',
            'role_name': 'Team Lead',
            'hierarchy_level': 50,
            'organization': org,
            'department': teamlead.department,
            'team': None,
            'profile_id': str(teamlead.id),
            'permissions': perms,
            'available_roles': [{'code': 'team_lead', 'name': 'Team Lead', 'hierarchy_level': 50}],
        }

    # 4. Check Employee
    if employee:
        from permitions.models import RolePermission
        elevated_codes = {'super_admin', 'org_admin', 'manager', 'team_lead', 'lead_portal'}
        role_objects = list(
            employee.additional_roles.filter(
                models.Q(organization=org) | models.Q(organization__isnull=True)
            ).exclude(code__in=elevated_codes).order_by('code', 'name', 'id')
        )
        if (
            employee.role
            and employee.role.organization_id in (None, getattr(org, 'id', None))
            and employee.role.code not in elevated_codes
            and all(role.id != employee.role_id for role in role_objects)
        ):
            role_objects.insert(0, employee.role)
        # Prefer the primary role when a system role and organization role
        # happen to share a code. The header still selects only assigned roles.
        role_by_code = {}
        for role in role_objects:
            role_by_code.setdefault(role.code, role)
        requested_code = request.headers.get('X-Active-Role') if request and hasattr(request, 'headers') else None
        role_obj = role_by_code.get(requested_code) or (employee.role if employee.role and employee.role.organization_id in (None, getattr(org,'id',None)) else None)
        if role_obj and role_obj.code in elevated_codes:
            role_obj = None
        if role_obj and all(role.id != role_obj.id for role in role_objects):
            role_objects.insert(0, role_obj)
        role_code = role_obj.code if role_obj else 'general_employee'
        role_name = role_obj.name if role_obj else 'General Employee'
        perms = []
        if role_obj:
            perms = list(RolePermission.objects.filter(role=role_obj).values_list('permission__codename', flat=True))

        return {
            'role_code': role_code,
            'role_name': role_name,
            'hierarchy_level': 30,
            'organization': org,
            'department': employee.department,
            'team': employee.team,
            'profile_id': str(employee.id),
            'permissions': perms,
            'available_roles': [
                {'code': role.code, 'name': role.name, 'hierarchy_level': 30}
                for role in role_objects
            ] or [{'code': role_code, 'name': role_name, 'hierarchy_level': 30}],
        }

    return {
        'role_code': 'org_user',
        'role_name': 'User',
        'hierarchy_level': 10,
        'organization': org,
        'department': None,
        'team': None,
        'profile_id': str(user.id),
        'permissions': [],
        'available_roles': [],
    }


class TenantQuerySetMixin:
    """
    Mixin for ModelViewSets or GenericAPIViews to automatically filter querysets
    by the authenticated user's organization.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_superuser:
            return qs

        org = get_user_organization(user)
        if not org:
            return qs.none()

        model = qs.model
        if hasattr(model, 'organization'):
            return qs.filter(organization=org)
        elif hasattr(model, 'default_organization'):
            return qs.filter(default_organization=org)
        return qs
