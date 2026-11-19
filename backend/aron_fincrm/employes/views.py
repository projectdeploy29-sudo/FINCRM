from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from employes.models import Employee, EmployeeAssignmentHistory
from accounts.models import Manager, TeamLead
from employes.serializers import (
    EmployeeSerializer,
    ManagerSerializer,
    TeamLeadSerializer,
    StaffOnboardingSerializer,
    EmployeeAssignmentHistorySerializer,
)
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import (
    IsAuthenticatedTenant,
    IsOrgAdmin,
    IsManager,
    IsTeamLead,
    IsEmployee,
)


class StaffOnboardingView(APIView):
    """
    POST /api/v1/staff/onboard/
    Unified onboarding for Managers, Team Leads, and Employees with automatic User creation.
    """
    permission_classes = [IsAuthenticatedTenant]

    def post(self, request):
        serializer = StaffOnboardingSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmployeeViewSet(viewsets.ModelViewSet):
    """
    CRUD for Employees with hierarchical data scoping:
    - Org Admin: Sees all employees in the organization.
    - Manager: Sees employees in managed departments and teams.
    - Team Lead: Sees employees in their assigned team.
    - Employee: Sees their own employee profile.
    """
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticatedTenant]

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user)
        if not org:
            return Employee.objects.none()

        role_ctx = get_user_role_context(user, self.request)
        level = role_ctx['hierarchy_level']

        base_qs = Employee.objects.filter(organization=org).select_related(
            'user', 'department', 'team', 'role', 'manager__user'
        ).order_by('employee_code')
        role_code=self.request.query_params.get('role_code')
        if role_code:
            role_matches=base_qs.filter(Q(role__code=role_code)|Q(additional_roles__code=role_code))
            if get_user_role_context(user,self.request)['hierarchy_level']<50:
                own=getattr(user,'employee',None)
                base_qs=role_matches.filter(team=own.team) if own and own.team_id else role_matches.none()
            else:
                base_qs=role_matches
            base_qs=base_qs.distinct()

        # 1. Org Admin / Superuser: full visibility
        if level >= 90:
            return base_qs

        # 2. Manager: departments they manage
        if level >= 70:
            manager = getattr(user, 'manager_set', None)
            if manager and manager.exists():
                mgr = manager.first()
                managed_depts = mgr.managed_departments.values_list('id', flat=True)
                return base_qs.filter(
                    Q(department_id__in=managed_depts) |
                    Q(manager__user=user)
                )
            return base_qs.none()

        # 3. Team Lead: team they lead
        if level >= 50:
            tl_qs = getattr(user, 'teamlead_profiles', None)
            if tl_qs and tl_qs.exists():
                tl = tl_qs.first()
                led_teams = tl.teams.values_list('id', flat=True)
                return base_qs.filter(team_id__in=led_teams)
            return base_qs

        # 4. Employee: self only
        return base_qs.filter(user=user)

    def create(self,request,*args,**kwargs):
        payload={key:request.data.get(key) for key in ('username','email','password','first_name','last_name','designation','work_email','work_phone','join_date') if key in request.data}
        payload.update({'staff_type':'employee','code':request.data.get('code') or request.data.get('employee_code')})
        for source,target in (('department','department_id'),('team','team_id'),('role','role_id'),('manager','reporting_manager_id')):
            if request.data.get(source): payload[target]=request.data[source]
        if request.data.get('role_ids') is not None: payload['role_ids']=request.data.getlist('role_ids') if hasattr(request.data,'getlist') else request.data.get('role_ids')
        serializer=StaffOnboardingSerializer(data=payload,context={'request':request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(),status=status.HTTP_201_CREATED)

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticatedTenant(), IsTeamLead()]
        elif self.action in ['destroy']:
            return [IsAuthenticatedTenant(), IsOrgAdmin()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticatedTenant(), IsTeamLead()]
        return [IsAuthenticatedTenant()]

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        GET /api/v1/staff/employees/<id>/history/
        Returns assignment and promotion history for the employee.
        """
        employee = self.get_object()
        history_records = EmployeeAssignmentHistory.objects.filter(
            employee=employee
        ).select_related(
            'previous_department', 'new_department',
            'previous_team', 'new_team',
            'previous_role', 'new_role',
            'changed_by'
        ).order_by('-changed_at')
        serializer = EmployeeAssignmentHistorySerializer(history_records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ManagerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/v1/staff/managers/
    List and retrieve Managers in the organization.
    """
    serializer_class = ManagerSerializer
    permission_classes = [IsAuthenticatedTenant, IsManager]

    def get_queryset(self):
        org = get_user_organization(self.request.user,self.request)
        if not org:
            return Manager.objects.none()
        qs=Manager.objects.filter(organization=org).select_related('user').prefetch_related('managed_departments').order_by('code')
        ctx=get_user_role_context(self.request.user,self.request)
        if 70<=ctx['hierarchy_level']<90:qs=qs.filter(user=self.request.user)
        return qs


class TeamLeadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/v1/staff/team-leads/
    List and retrieve Team Leads in the organization.
    """
    serializer_class = TeamLeadSerializer
    permission_classes = [IsAuthenticatedTenant, IsTeamLead]

    def get_queryset(self):
        org = get_user_organization(self.request.user,self.request)
        if not org:
            return TeamLead.objects.none()
        qs=TeamLead.objects.filter(organization=org).select_related('user', 'department', 'manager__user').prefetch_related('teams').order_by('code')
        ctx=get_user_role_context(self.request.user,self.request)
        if 50<=ctx['hierarchy_level']<70:
            qs=qs.filter(user=self.request.user)
        elif 70<=ctx['hierarchy_level']<90:
            manager=self.request.user.manager_set.first() if hasattr(self.request.user,'manager_set') else None
            qs=qs.filter(department__in=manager.managed_departments.all()) if manager else qs.none()
        return qs
