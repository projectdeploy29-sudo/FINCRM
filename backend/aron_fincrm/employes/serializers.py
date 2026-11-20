import uuid
from django.db import transaction
from django.db.models import Q
from django.utils.crypto import get_random_string
from rest_framework import serializers
from django.contrib.auth import get_user_model
from employes.models import Employee, EmployeeAssignmentHistory
from accounts.models import Manager, TeamLead
from organizations.models import Department, Team
from permitions.models import Role
from organizations.tenant import get_user_organization, get_user_role_context

User = get_user_model()
ELEVATED_ROLE_CODES = {'super_admin', 'org_admin', 'manager', 'team_lead', 'lead_portal'}


def is_employee_role(role):
    """Employee profiles can carry multiple roles, all capped at employee scope."""
    return bool(role and role.code not in ELEVATED_ROLE_CODES)


class EmployeeAssignmentHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField(read_only=True)
    previous_dept_name = serializers.CharField(source='previous_department.name', read_only=True)
    new_dept_name = serializers.CharField(source='new_department.name', read_only=True)
    previous_team_name = serializers.CharField(source='previous_team.name', read_only=True)
    new_team_name = serializers.CharField(source='new_team.name', read_only=True)
    previous_role_name = serializers.CharField(source='previous_role.name', read_only=True)
    new_role_name = serializers.CharField(source='new_role.name', read_only=True)

    class Meta:
        model = EmployeeAssignmentHistory
        fields = [
            'id',
            'previous_dept_name',
            'new_dept_name',
            'previous_team_name',
            'new_team_name',
            'previous_role_name',
            'new_role_name',
            'reason',
            'changed_by_name',
            'changed_at',
        ]

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return None


class EmployeeSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField(read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    role_details = serializers.SerializerMethodField(read_only=True)
    roles = serializers.SerializerMethodField(read_only=True)
    role_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    manager_name = serializers.SerializerMethodField(read_only=True)
    change_reason = serializers.CharField(write_only=True, required=False, default="")

    class Meta:
        model = Employee
        fields = [
            'id',
            'user',
            'user_details',
            'employee_code',
            'department',
            'department_name',
            'team',
            'team_name',
            'role',
            'role_details',
            'roles',
            'role_ids',
            'manager',
            'manager_name',
            'work_email',
            'work_phone',
            'designation',
            'join_date',
            'employment_status',
            'change_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_user_details(self, obj):
        u = obj.user
        return {
            'id': str(u.id),
            'username': u.username,
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'full_name': u.get_full_name() or u.username,
        }

    def get_role_details(self, obj):
        if not obj.role:
            return None
        return {
            'id': str(obj.role.id),
            'name': obj.role.name,
            'code': obj.role.code,
        }

    def get_roles(self, obj):
        roles = list(obj.additional_roles.all())
        if obj.role_id and all(role.id != obj.role_id for role in roles):
            roles.insert(0, obj.role)
        return [{'id': str(role.id), 'name': role.name, 'code': role.code} for role in roles]

    def get_manager_name(self, obj):
        if obj.manager and obj.manager.user:
            return obj.manager.user.get_full_name() or obj.manager.user.username
        return None

    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req)
        checks=(('department',attrs.get('department')),('team',attrs.get('team')),('role',attrs.get('role')),('manager',attrs.get('manager')))
        for name,obj in checks:
            if obj and name!='role' and obj.organization_id!=org.id: raise serializers.ValidationError({name:'Choose a record in your organization.'})
            if obj and name=='role' and obj.organization_id not in (None,org.id): raise serializers.ValidationError({name:'Choose a system or organization role.'})
        assignment_changed=not self.instance or any(
            key in attrs and attrs[key] != getattr(self.instance,key)
            for key in ('department','team')
        )
        if assignment_changed and attrs.get('department',getattr(self.instance,'department',None)) and not attrs.get('department',getattr(self.instance,'department',None)).is_active:
            raise serializers.ValidationError({'department':'Choose an active department.'})
        if assignment_changed and attrs.get('team',getattr(self.instance,'team',None)) and not attrs.get('team',getattr(self.instance,'team',None)).is_active:
            raise serializers.ValidationError({'team':'Choose an active team.'})
        team=attrs.get('team', getattr(self.instance, 'team', None)); dept=attrs.get('department', getattr(self.instance, 'department', None))
        if team and dept and team.department_id!=dept.id: raise serializers.ValidationError({'team':'Team must belong to the selected department.'})
        ctx=get_user_role_context(req.user,req); level=ctx['hierarchy_level']; user=req.user
        if 70<=level<90:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            departments=manager.managed_departments.all() if manager else Department.objects.none()
            if dept and not departments.filter(pk=dept.pk).exists():
                raise serializers.ValidationError({'department':'Choose a department managed by you.'})
        elif 50<=level<70:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            led_teams=profile.teams.all() if profile else Team.objects.none()
            if not team or not led_teams.filter(pk=team.pk).exists():
                raise serializers.ValidationError({'team':'Choose a team assigned to you.'})
        reporting_manager=attrs.get('manager',getattr(self.instance,'manager',None))
        if reporting_manager and reporting_manager.employment_status!=Employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'manager':'Choose an active reporting employee.'})
        if reporting_manager and dept and reporting_manager.department_id!=dept.id:
            raise serializers.ValidationError({'manager':'Reporting employee must belong to the selected department.'})
        if reporting_manager and self.instance:
            if reporting_manager.pk==self.instance.pk:
                raise serializers.ValidationError({'manager':'An employee cannot report to themselves.'})
            seen=set()
            cursor=reporting_manager
            while cursor and cursor.pk not in seen:
                if cursor.pk==self.instance.pk:
                    raise serializers.ValidationError({'manager':'This reporting change would create a hierarchy cycle.'})
                seen.add(cursor.pk)
                cursor=cursor.manager
        role_ids = attrs.get('role_ids')
        if role_ids is not None:
            role_map = {role.id:role for role in Role.objects.filter(id__in=role_ids).filter(Q(organization=org)|Q(organization__isnull=True))}
            if len(role_map) != len(set(role_ids)):
                raise serializers.ValidationError({'role_ids':'Choose only system or organization roles.'})
            attrs['_selected_roles'] = [role_map[role_id] for role_id in role_ids]
            if any(not is_employee_role(role) for role in attrs['_selected_roles']):
                raise serializers.ValidationError({'role_ids':'Employees can only be assigned employee-level roles.'})
        elif attrs.get('role') and not is_employee_role(attrs['role']):
            raise serializers.ValidationError({'role':'Choose an employee-level role.'})
        return attrs

    def update(self, instance, validated_data):
        change_reason = validated_data.pop('change_reason', '')
        request = self.context.get('request')
        current_user = request.user if request else None

        prev_dept = instance.department
        prev_team = instance.team
        prev_role = instance.role
        prev_role_ids = set(instance.additional_roles.values_list('id', flat=True))
        prev_manager = instance.manager

        with transaction.atomic():
            selected_roles = validated_data.pop('_selected_roles', None)
            role_ids = validated_data.pop('role_ids', None)
            updated_instance = super().update(instance, validated_data)
            if selected_roles is not None or role_ids is not None:
                roles = selected_roles or []
                updated_instance.role = roles[0] if roles else None
                updated_instance.save(update_fields=['role'])
                updated_instance.additional_roles.set(roles[1:])

            # Check if assignment changed
            changed = (
                prev_dept != updated_instance.department or
                prev_team != updated_instance.team or
                prev_role != updated_instance.role or
                prev_role_ids != set(updated_instance.additional_roles.values_list('id', flat=True)) or
                prev_manager != updated_instance.manager
            )

            if changed and current_user:
                EmployeeAssignmentHistory.objects.create(
                    employee=updated_instance,
                    previous_department=prev_dept,
                    new_department=updated_instance.department,
                    previous_team=prev_team,
                    new_team=updated_instance.team,
                    previous_role=prev_role,
                    new_role=updated_instance.role,
                    previous_manager=prev_manager,
                    new_manager=updated_instance.manager,
                    changed_by=current_user,
                    reason=change_reason or "Staff profile assignment update",
                )

            return updated_instance


class ManagerSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField(read_only=True)
    managed_departments = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Manager
        fields = [
            'id',
            'user',
            'user_details',
            'code',
            'work_email',
            'work_phone',
            'designation',
            'join_date',
            'employment_status',
            'managed_departments',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_user_details(self, obj):
        u = obj.user
        return {
            'id': str(u.id),
            'username': u.username,
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'full_name': u.get_full_name() or u.username,
        }

    def get_managed_departments(self, obj):
        return list(obj.managed_departments.values('id', 'name'))

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            sync_staff_account_status(instance)
        return instance


class TeamLeadSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField(read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    manager_name = serializers.SerializerMethodField(read_only=True)
    led_teams = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TeamLead
        fields = [
            'id',
            'user',
            'user_details',
            'code',
            'department',
            'department_name',
            'manager',
            'manager_name',
            'work_email',
            'work_phone',
            'designation',
            'join_date',
            'employment_status',
            'led_teams',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_user_details(self, obj):
        u = obj.user
        if not u:
            return None
        return {
            'id': str(u.id),
            'username': u.username,
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'full_name': u.get_full_name() or u.username,
        }

    def get_manager_name(self, obj):
        if obj.manager and obj.manager.user:
            return obj.manager.user.get_full_name() or obj.manager.user.username
        return None

    def get_led_teams(self, obj):
        return list(obj.teams.values('id', 'name'))

    def validate(self, attrs):
        request = self.context.get('request')
        organization = get_user_organization(request.user, request) if request else None
        department = attrs.get('department')
        manager = attrs.get('manager')
        if department and (not organization or department.organization_id != organization.id):
            raise serializers.ValidationError({'department': 'Department must belong to your organization.'})
        if department and not department.is_active:
            raise serializers.ValidationError({'department': 'Choose an active department.'})
        if manager and (not organization or manager.organization_id != organization.id):
            raise serializers.ValidationError({'manager': 'Manager must belong to your organization.'})
        if manager and manager.employment_status != Manager.ManagerStatus.ACTIVE:
            raise serializers.ValidationError({'manager': 'Choose an active manager.'})
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            sync_staff_account_status(instance)
        return instance


def sync_staff_account_status(profile):
    """Keep staff account login state aligned with employment status."""
    user = profile.user
    should_be_active = profile.employment_status == 'active'
    if user and user.is_active != should_be_active:
        user.is_active = should_be_active
        user.save(update_fields=['is_active'])


class StaffOnboardingSerializer(serializers.Serializer):
    """
    Unified staff onboarding serializer:
    Creates User + Profile (Manager, TeamLead, or Employee) in one atomic transaction.
    """
    STAFF_TYPES = (
        ('manager', 'Manager'),
        ('team_lead', 'Team Lead'),
        ('employee', 'Employee'),
    )

    staff_type = serializers.ChoiceField(choices=STAFF_TYPES)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    code = serializers.CharField(max_length=50)
    designation = serializers.CharField(max_length=100, required=False, allow_blank=True)
    work_email = serializers.EmailField(required=False, allow_blank=True)
    work_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    join_date = serializers.DateField(required=False, allow_null=True)

    # Scoping fields
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    team_id = serializers.UUIDField(required=False, allow_null=True)
    role_id = serializers.UUIDField(required=False, allow_null=True)
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    reporting_manager_id = serializers.UUIDField(required=False, allow_null=True)
    reporting_employee_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        role_ctx = get_user_role_context(user, request)
        staff_type = attrs['staff_type']

        # Resolve organization
        org = get_user_organization(user, request)
        if not org:
            raise serializers.ValidationError({
                "organization": "No organization context found. Please ensure the user has an organization or provide 'organization_id'."
            })
        attrs['organization'] = org

        department_id=attrs.get('department_id'); team_id=attrs.get('team_id'); role_id=attrs.get('role_id')
        reporting_id = attrs.get('reporting_manager_id') if staff_type == 'team_lead' else attrs.get('reporting_employee_id', attrs.get('reporting_manager_id'))
        department=Department.objects.filter(id=department_id,organization=org).first() if department_id else None
        team=Team.objects.filter(id=team_id,organization=org).first() if team_id else None
        if department_id and not department: raise serializers.ValidationError({'department_id':'Department was not found in your organization.'})
        if team_id and not team: raise serializers.ValidationError({'team_id':'Team was not found in your organization.'})
        if department and not department.is_active: raise serializers.ValidationError({'department_id':'Choose an active department.'})
        if team and not team.is_active: raise serializers.ValidationError({'team_id':'Choose an active team.'})
        if team and department and team.department_id!=department.id: raise serializers.ValidationError({'team_id':'Team must belong to the selected department.'})
        if staff_type=='team_lead' and not department:
            raise serializers.ValidationError({'department_id':'Choose the team lead’s department.'})
        if role_id and not Role.objects.filter(id=role_id).filter(Q(organization=org)|Q(organization__isnull=True)).exists(): raise serializers.ValidationError({'role_id':'Role was not found in your organization.'})
        if role_id:
            selected_role=Role.objects.filter(id=role_id).first()
            if selected_role and not is_employee_role(selected_role): raise serializers.ValidationError({'role_id':'Employees can only be assigned employee-level roles.'})
        if attrs.get('role_ids'):
            role_map={role.id:role for role in Role.objects.filter(id__in=attrs['role_ids']).filter(Q(organization=org)|Q(organization__isnull=True))}
            if len(role_map)!=len(set(attrs['role_ids'])): raise serializers.ValidationError({'role_ids':'Choose only system or organization roles.'})
            attrs['_selected_roles']=[role_map[role_id] for role_id in attrs['role_ids']]
            if any(not is_employee_role(role) for role in attrs['_selected_roles']): raise serializers.ValidationError({'role_ids':'Employees can only be assigned employee-level roles.'})
        reporting_manager=Manager.objects.filter(id=reporting_id,organization=org).first() if staff_type=='team_lead' and reporting_id else None
        if staff_type=='team_lead' and reporting_id and not reporting_manager:
            raise serializers.ValidationError({'reporting_manager_id':'Manager was not found in your organization.'})
        if reporting_manager and reporting_manager.employment_status!=Manager.ManagerStatus.ACTIVE:
            raise serializers.ValidationError({'reporting_manager_id':'Choose an active manager.'})
        reporting_employee=Employee.objects.filter(id=reporting_id,organization=org).first() if staff_type=='employee' and reporting_id else None
        if staff_type=='employee' and reporting_id and not reporting_employee:
            raise serializers.ValidationError({'reporting_employee_id':'Reporting employee was not found in your organization.'})
        if reporting_employee and reporting_employee.employment_status!=Employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'reporting_employee_id':'Choose an active reporting employee.'})
        if reporting_employee and department and reporting_employee.department_id!=department.id:
            raise serializers.ValidationError({'reporting_employee_id':'Reporting employee must belong to the selected department.'})
        if reporting_employee and role_ctx['hierarchy_level']<70 and team and reporting_employee.team_id!=team.id:
            raise serializers.ValidationError({'reporting_employee_id':'Reporting employee must belong to the selected team.'})

        # Enforce Hierarchy Creation Rights:
        # 1. Org Admin / Super Admin can create Manager, Team Lead, Employee
        # 2. Manager can create Team Lead, Employee
        # 3. Team Lead can create Employee in their team
        level = role_ctx['hierarchy_level']
        if staff_type == 'manager' and level < 90:
            raise serializers.ValidationError({"staff_type": "Only Organization Admins can create Managers."})
        elif staff_type == 'team_lead' and level < 70:
            raise serializers.ValidationError({"staff_type": "Only Managers or Admins can create Team Leads."})
        elif staff_type == 'employee' and level < 50:
            raise serializers.ValidationError({"staff_type": "Only Team Leads, Managers, or Organization Admins can create employees."})

        # Managers and team leads can only provision staff inside their own hierarchy.
        if staff_type in ('team_lead', 'employee') and 70 <= level < 90:
            manager = getattr(user, 'manager_set', None)
            manager = manager.first() if manager and manager.exists() else None
            managed_departments = manager.managed_departments.all() if manager else Department.objects.none()
            if department and not managed_departments.filter(pk=department.pk).exists():
                raise serializers.ValidationError({'department_id': 'Choose a department managed by you.'})
            if staff_type == 'employee' and team and not team.department_id in managed_departments.values_list('id', flat=True):
                raise serializers.ValidationError({'team_id': 'Choose a team in one of your managed departments.'})
            if staff_type == 'team_lead' and not department:
                raise serializers.ValidationError({'department_id': 'A managed department is required for a team lead.'})
            if staff_type == 'team_lead' and manager:
                if attrs.get('reporting_manager_id') and str(attrs['reporting_manager_id']) != str(manager.id):
                    raise serializers.ValidationError({'reporting_manager_id':'A manager can only assign a team lead to their own manager profile.'})
                attrs['reporting_manager_id']=manager.id
        elif staff_type == 'employee' and 50 <= level < 70:
            profile = getattr(user, 'teamlead_profiles', None)
            profile = profile.first() if profile and profile.exists() else None
            led_teams = profile.teams.all() if profile else Team.objects.none()
            if not team or not led_teams.filter(pk=team.pk).exists():
                raise serializers.ValidationError({'team_id': 'Choose a team assigned to you.'})
            department = team.department
            attrs['department_id'] = department.pk
        elif staff_type == 'employee' and level < 50:
            creator=getattr(user,'employee',None)
            if creator and not team:
                team=creator.team
                attrs['team_id']=creator.team_id
            if creator and not department:
                department=creator.department
                attrs['department_id']=creator.department_id
            if not creator or not creator.team_id or not team or team.pk != creator.team_id:
                raise serializers.ValidationError({'team_id':'Employees may only create employee accounts in their own team.'})
            department=team.department
            attrs['department_id']=department.pk
            selected=attrs.get('_selected_roles',[])
            if any(not is_employee_role(role) for role in selected):
                raise serializers.ValidationError({'role_ids':'Employees may only assign employee-level roles.'})

        from subscriptions.entitlements import enforce_resource_limit
        enforce_resource_limit(org, 'employees')

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        current_user = request.user
        org = validated_data.pop('organization', None) or get_user_organization(current_user, request)


        staff_type = validated_data.pop('staff_type')
        username = validated_data.pop('username')
        email = validated_data.pop('email')
        raw_password = validated_data.pop('password', None)
        if not raw_password:
            raw_password = get_random_string(10)

        first_name = validated_data.pop('first_name', '')
        last_name = validated_data.pop('last_name', '')
        code = validated_data.pop('code')
        designation = validated_data.pop('designation', '')
        work_email = validated_data.pop('work_email', '') or email
        work_phone = validated_data.pop('work_phone', '')
        join_date = validated_data.pop('join_date', None)

        department_id = validated_data.pop('department_id', None)
        team_id = validated_data.pop('team_id', None)
        role_id = validated_data.pop('role_id', None)
        selected_roles = validated_data.pop('_selected_roles', None)
        role_ids = validated_data.pop('role_ids', None)
        if selected_roles is None and role_ids:
            selected_roles=list(Role.objects.filter(id__in=role_ids).filter(Q(organization=org)|Q(organization__isnull=True)))
        if selected_roles and not role_id:
            role_id=selected_roles[0].id
        reporting_manager_id = validated_data.pop('reporting_manager_id', None)
        reporting_employee_id = validated_data.pop('reporting_employee_id', reporting_manager_id)

        with transaction.atomic():
            from subscriptions.entitlements import enforce_resource_limit
            enforce_resource_limit(org, 'employees', lock=True)
            # 1. Create Base User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=raw_password,
                first_name=first_name,
                last_name=last_name,
                default_organization=org,
            )

            profile_data = {}
            if staff_type == 'manager':
                manager_obj = Manager.objects.create(
                    organization=org,
                    user=user,
                    code=code,
                    work_email=work_email,
                    work_phone=work_phone,
                    designation=designation or "Manager",
                    join_date=join_date,
                    employment_status='active',
                )
                profile_data = ManagerSerializer(manager_obj).data

            elif staff_type == 'team_lead':
                department = Department.objects.filter(id=department_id, organization=org).first() if department_id else None
                reporting_mgr = Manager.objects.filter(id=reporting_manager_id, organization=org).first() if reporting_manager_id else None

                tl_obj = TeamLead.objects.create(
                    organization=org,
                    user=user,
                    code=code,
                    department=department,
                    manager=reporting_mgr,
                    work_email=work_email,
                    work_phone=work_phone,
                    designation=designation or "Team Lead",
                    join_date=join_date,
                    employment_status='active',
                )
                profile_data = TeamLeadSerializer(tl_obj).data

            elif staff_type == 'employee':
                department = Department.objects.filter(id=department_id, organization=org).first() if department_id else None
                team = Team.objects.filter(id=team_id, organization=org).first() if team_id else None
                role_obj = Role.objects.filter(id=role_id).first() if role_id else None
                if not role_obj:
                    # Default to General Employee role
                    role_obj = Role.objects.filter(code='general_employee').first()

                reporting_emp = Employee.objects.filter(id=reporting_employee_id, organization=org).first() if reporting_employee_id else None

                emp_obj = Employee.objects.create(
                    organization=org,
                    user=user,
                    employee_code=code,
                    department=department,
                    team=team,
                    role=role_obj,
                    manager=reporting_emp,
                    work_email=work_email,
                    work_phone=work_phone,
                    designation=designation or (role_obj.name if role_obj else "Employee"),
                    join_date=join_date,
                    employment_status='active',
                )
                if selected_roles:
                    if emp_obj.role_id != selected_roles[0].id:
                        emp_obj.role=selected_roles[0]
                        emp_obj.save(update_fields=['role'])
                    emp_obj.additional_roles.set([role for role in selected_roles if role.id != emp_obj.role_id])

                # Log initial assignment history
                EmployeeAssignmentHistory.objects.create(
                    employee=emp_obj,
                    new_department=department,
                    new_team=team,
                    new_role=role_obj,
                    new_manager=reporting_emp,
                    changed_by=current_user,
                    reason="Initial staff onboarding",
                )
                profile_data = EmployeeSerializer(emp_obj).data

            return {
                'staff_type': staff_type,
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'initial_password': raw_password,
                },
                'profile': profile_data,
            }
