from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from organizations.models import organizations_organization
from organizations.serializers import (
    OrganizationSerializer,
    OrganizationRegistrationSerializer,
)
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin, IsManager, IsTeamLead


class OrganizationRegistrationView(APIView):
    """
    POST /api/v1/organizations/register/
    Public endpoint to onboard a new finance organization (tenant) and its initial Org Admin user.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OrganizationRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CurrentOrganizationView(APIView):
    """
    GET, PATCH /api/v1/organizations/current/
    Inspect or update the authenticated user's organization profile.
    """
    permission_classes = [IsAuthenticatedTenant]

    def get(self, request):
        from organizations.tenant import get_user_role_context
        from rest_framework.exceptions import PermissionDenied
        role=get_user_role_context(request.user,request); level=role['hierarchy_level']
        if level<50: raise PermissionDenied('Team lead or higher role required to view organization hierarchy.')
        org = get_user_organization(request.user,request)
        if not org:
            return Response({"detail": "No organization associated with this account."}, status=status.HTTP_404_NOT_FOUND)
        serializer = OrganizationSerializer(org)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        if not IsOrgAdmin().has_permission(request, self):
            return Response({"detail": "Only Organization Admins can modify organization settings."}, status=status.HTTP_403_FORBIDDEN)
        org = get_user_organization(request.user,request)
        if not org:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = OrganizationSerializer(org, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from rest_framework import viewsets
from django.db.models import Count
from organizations.models import Department, Team
from organizations.serializers import DepartmentSerializer, TeamSerializer
from permitions.permissions import IsManager
from accounts.models import Manager, TeamLead
from employes.models import Employee


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Departments within an organization.
    Annotated with team and employee counts.
    """
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticatedTenant, IsManager]

    def get_queryset(self):
        org = get_user_organization(self.request.user,self.request)
        if not org:
            return Department.objects.none()
        qs=Department.objects.filter(organization=org).select_related(
            'manager__user'
        ).annotate(
            teams_count=Count('team', distinct=True),
            employees_count=Count('employee', distinct=True),
        ).order_by('name')
        ctx=get_user_role_context(self.request.user,self.request)
        if 70<=ctx['hierarchy_level']<90:
            manager=self.request.user.manager_set.first() if hasattr(self.request.user,'manager_set') else None
            qs=qs.filter(manager=manager) if manager else qs.none()
        return qs

    def get_permissions(self):
        if self.action in ['create']:
            from permitions.permissions import IsOrgAdmin
            return [IsAuthenticatedTenant(), IsOrgAdmin()]
        return [IsAuthenticatedTenant(), IsManager()]


class TeamViewSet(viewsets.ModelViewSet):
    """
    CRUD for Teams within an organization and department.
    """
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticatedTenant, IsTeamLead]

    def get_queryset(self):
        org = get_user_organization(self.request.user,self.request)
        if not org:
            return Team.objects.none()
        qs = Team.objects.filter(organization=org).select_related(
            'department', 'team_lead__user', 'team_leader__user'
        ).annotate(
            members_count=Count('employee', distinct=True)
        ).order_by('name')

        dept_id = self.request.query_params.get('department')
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        role=get_user_role_context(self.request.user,self.request); level=role['hierarchy_level']; user=self.request.user
        if 50<=level<70:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            qs=qs.filter(team_lead=profile) if profile else qs.none()
        elif 70<=level<90:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            qs=qs.filter(department__in=manager.managed_departments.all()) if manager else qs.none()
        return qs

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticatedTenant(), IsManager()]
        return [IsAuthenticatedTenant(), IsTeamLead()]


class HierarchyTreeView(APIView):
    """
    GET /api/v1/hierarchy/tree/
    Returns the complete organizational hierarchy tree:
    Organization -> Departments (with Manager) -> Teams (with Team Lead) -> Employees.
    """
    permission_classes = [IsAuthenticatedTenant]

    def get(self, request):
        role=get_user_role_context(request.user,request); level=role['hierarchy_level']
        if level<50:return Response({'detail':'Team lead or higher role required to view organization hierarchy.'},status=status.HTTP_403_FORBIDDEN)
        org = get_user_organization(request.user,request)
        if not org:
            return Response({"detail": "No organization found."}, status=status.HTTP_404_NOT_FOUND)

        departments = Department.objects.filter(organization=org).select_related('manager__user')
        teams = Team.objects.filter(organization=org).select_related('team_lead__user', 'team_leader__user', 'department')
        employees = Employee.objects.filter(organization=org).select_related('user', 'role', 'department', 'team')
        managers = Manager.objects.filter(organization=org).select_related('user')
        team_leads = TeamLead.objects.filter(organization=org).select_related('user', 'department')
        if 50<=level<70:
            profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
            led_teams=profile.teams.all() if profile else Team.objects.none()
            teams=teams.filter(id__in=led_teams.values('id'))
            employees=employees.filter(team__in=led_teams)
            departments=departments.filter(id__in=teams.values('department_id'))
            team_leads=team_leads.filter(teams__in=led_teams).distinct()
            managers=Manager.objects.none()
        elif 70<=level<90:
            manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
            departments=departments.filter(manager=manager) if manager else Department.objects.none()
            teams=teams.filter(department__in=departments); employees=employees.filter(department__in=departments)
            team_leads=team_leads.filter(department__in=departments); managers=managers.filter(managed_departments__in=departments).distinct()

        if 50<=level<70:
            profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
            led_teams=profile.teams.all() if profile else Team.objects.none()
            teams=teams.filter(id__in=led_teams.values('id'))
            employees=employees.filter(team__in=led_teams)
            departments=departments.filter(id__in=teams.values('department_id'))
            team_leads=team_leads.filter(teams__in=led_teams).distinct()
            managers=Manager.objects.none()
        elif 70<=level<90:
            manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
            departments=departments.filter(manager=manager) if manager else Department.objects.none()
            teams=teams.filter(department__in=departments); employees=employees.filter(department__in=departments)
            team_leads=team_leads.filter(department__in=departments); managers=managers.filter(managed_departments__in=departments).distinct()

        # Index employees by team and department
        team_employees = {}
        dept_unassigned_employees = {}
        unassigned_employees = []

        for emp in employees:
            emp_data = {
                'id': str(emp.id),
                'code': emp.employee_code,
                'name': emp.user.get_full_name() or emp.user.username,
                'email': emp.work_email or emp.user.email,
                'phone': emp.work_phone,
                'designation': emp.designation,
                'role': {
                    'code': emp.role.code if emp.role else 'general_employee',
                    'name': emp.role.name if emp.role else 'General Employee',
                } if emp.role else None,
                'employment_status': emp.employment_status,
            }

            if emp.team_id:
                team_employees.setdefault(str(emp.team_id), []).append(emp_data)
            elif emp.department_id:
                dept_unassigned_employees.setdefault(str(emp.department_id), []).append(emp_data)
            else:
                unassigned_employees.append(emp_data)

        # Index teams by department
        dept_teams = {}
        unassigned_teams = []

        for team in teams:
            tl = team.team_lead
            tl_user = tl.user if tl else None
            t_data = {
                'id': str(team.id),
                'name': team.name,
                'description': team.description,
                'is_active': team.is_active,
                'team_lead': {
                    'id': str(tl.id),
                    'code': tl.code,
                    'name': (tl_user.get_full_name() or tl_user.username) if tl_user else tl.code,
                    'email': tl.work_email or (tl_user.email if tl_user else ''),
                    'phone': tl.work_phone,
                } if tl else None,
                'employees': team_employees.get(str(team.id), []),
            }

            if team.department_id:
                dept_teams.setdefault(str(team.department_id), []).append(t_data)
            else:
                unassigned_teams.append(t_data)

        # Build department nodes
        department_nodes = []
        for dept in departments:
            mgr = dept.manager
            mgr_user = mgr.user if mgr else None
            department_nodes.append({
                'id': str(dept.id),
                'name': dept.name,
                'description': dept.description,
                'is_active': dept.is_active,
                'manager': {
                    'id': str(mgr.id),
                    'code': mgr.code,
                    'name': (mgr_user.get_full_name() or mgr_user.username) if mgr_user else mgr.code,
                    'email': mgr.work_email or (mgr_user.email if mgr_user else ''),
                    'phone': mgr.work_phone,
                    'designation': mgr.designation,
                } if mgr else None,
                'teams': dept_teams.get(str(dept.id), []),
                'unassigned_team_employees': dept_unassigned_employees.get(str(dept.id), []),
            })

        tree = {
            'organization': {
                'id': str(org.id),
                'name': org.name,
                'slug': org.slug,
                'currency': getattr(org, 'currency', 'INR'),
            },
            'departments': department_nodes,
            'unassigned_teams': unassigned_teams,
            'unassigned_employees': unassigned_employees,
            'total_departments': len(department_nodes),
            'total_teams': len(teams),
            'total_employees': len(employees),
            'total_managers': len(managers),
            'total_team_leads': len(team_leads),
        }
        return Response(tree, status=status.HTTP_200_OK)
