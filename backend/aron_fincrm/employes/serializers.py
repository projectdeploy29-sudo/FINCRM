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
EMPLOYEE_ROLE_CODES = {'general_employee', 'doc_officer', 'document_verification_officer', 'finance_analyst', 'financial_analyst', 'sales_analyst'}


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
        team=attrs.get('team'); dept=attrs.get('department')
        if team and dept and team.department_id!=dept.id: raise serializers.ValidationError({'team':'Team must belong to the selected department.'})
        role_ids = attrs.get('role_ids')
        if role_ids is not None:
            role_map = {role.id:role for role in Role.objects.filter(id__in=role_ids).filter(Q(organization=org)|Q(organization__isnull=True))}
            if len(role_map) != len(set(role_ids)):
                raise serializers.ValidationError({'role_ids':'Choose only system or organization roles.'})
            attrs['_selected_roles'] = [role_map[role_id] for role_id in role_ids]
            if any(role.code not in EMPLOYEE_ROLE_CODES for role in attrs['_selected_roles']):
                raise serializers.ValidationError({'role_ids':'Employees can only be assigned employee-level roles.'})
        elif attrs.get('role') and attrs['role'].code not in EMPLOYEE_ROLE_CODES:
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
        if team and department and team.department_id!=department.id: raise serializers.ValidationError({'team_id':'Team must belong to the selected department.'})
        if staff_type=='team_lead' and not department:
            raise serializers.ValidationError({'department_id':'Choose the team lead’s department.'})
        if role_id and not Role.objects.filter(id=role_id).filter(Q(organization=org)|Q(organization__isnull=True)).exists(): raise serializers.ValidationError({'role_id':'Role was not found in your organization.'})
        if role_id:
            selected_role=Role.objects.filter(id=role_id).first()
            if selected_role and selected_role.code not in EMPLOYEE_ROLE_CODES: raise serializers.ValidationError({'role_id':'Employees can only be assigned employee-level roles.'})
        if attrs.get('role_ids'):
            role_map={role.id:role for role in Role.objects.filter(id__in=attrs['role_ids']).filter(Q(organization=org)|Q(organization__isnull=True))}
            if len(role_map)!=len(set(attrs['role_ids'])): raise serializers.ValidationError({'role_ids':'Choose only system or organization roles.'})
            attrs['_selected_roles']=[role_map[role_id] for role_id in attrs['role_ids']]
            if any(role.code not in EMPLOYEE_ROLE_CODES for role in attrs['_selected_roles']): raise serializers.ValidationError({'role_ids':'Employees can only be assigned employee-level roles.'})
        if staff_type=='team_lead' and reporting_id and not Manager.objects.filter(id=reporting_id,organization=org).exists():
            raise serializers.ValidationError({'reporting_manager_id':'Manager was not found in your organization.'})
        if staff_type=='employee' and reporting_id and not Employee.objects.filter(id=reporting_id,organization=org).exists():
            raise serializers.ValidationError({'reporting_employee_id':'Reporting employee was not found in your organization.'})

        # Enforce Hierarchy Creation Rights:
        # 1. Org Admin / Super Admin can create Manager, Team Lead, Employee
        # 2. Manager can create Team Lead, Employee
        # 3. Team Lead can create Employee in their team
        level = role_ctx['hierarchy_level']
        if staff_type == 'manager' and level < 90:
            raise serializers.ValidationError({"staff_type": "Only Organization Admins can create Managers."})
        elif staff_type == 'team_lead' and level < 70:
            raise serializers.ValidationError({"staff_type": "Only Managers or Admins can create Team Leads."})
        elif staff_type == 'employee' and level < 30:
            raise serializers.ValidationError({"staff_type": "Permission denied to onboard employees."})

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
            if any(role.code!='general_employee' for role in selected):
                raise serializers.ValidationError({'role_ids':'Employees may only assign the General Employee role.'})

        # Check Subscription Tier Employee Limits
        from subscriptions.models import Subscription
        active_sub = Subscription.objects.filter(organization=org, status__in=['active','trialing']).order_by('-created_at').first()
        if active_sub and active_sub.plan:
            max_allowed = active_sub.plan.max_employees
            current_total = Employee.objects.filter(organization=org).count() + Manager.objects.filter(organization=org).count() + TeamLead.objects.filter(organization=org).count()
            if current_total >= max_allowed:
                raise serializers.ValidationError({
                    "subscription": f"Plan limit reached! Your current plan allows maximum {max_allowed} staff members. Please upgrade your subscription."
                })

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
