from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import Manager, TeamLead
from employes.models import Employee
from organizations.dates import (
    OrganizationDateTimeField,
    organization_local_date,
    organization_timezone,
)
from organizations.tenant import get_user_organization, get_user_role_context
from tasks.models import (
    Task,
    TaskHistory,
    CostomerFollowUp,
    LeadFollowUp,
)


class TaskSerializer(serializers.ModelSerializer):
    due_date = OrganizationDateTimeField()
    start_date = OrganizationDateTimeField(required=False, allow_null=True)

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = (
            'organization', 'assigned_by_user', 'assigned_by_manager',
            'assigned_by_teamlead', 'status', 'completed_at', 'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        request = self.context['request']
        user = request.user
        org = get_user_organization(user, request)
        instance = self.instance
        role = get_user_role_context(user, request)
        level = role['hierarchy_level']
        employee = getattr(user, 'employee', None)

        related_fields = (
            'assigned_to', 'department', 'team', 'related_customer',
            'related_lead',
        )
        for field in related_fields:
            related = attrs.get(field, getattr(instance, field, None))
            if related and getattr(related, 'organization_id', None) != getattr(org, 'id', None):
                raise serializers.ValidationError({field: 'This record must belong to your organization.'})

        manager = user.manager_set.first() if level >= 70 and hasattr(user, 'manager_set') else None
        profile = user.teamlead_profiles.first() if 50 <= level < 70 and hasattr(user, 'teamlead_profiles') else None

        for field in ('related_customer', 'related_lead'):
            target = attrs.get(field, getattr(instance, field, None))
            if not target:
                continue
            owner = target.assigned_to
            if level < 50 and (not employee or not owner or owner.id != employee.id):
                raise serializers.ValidationError({field: 'Related records must be assigned to you.'})
            if 50 <= level < 70 and (
                not profile or not owner or not profile.teams.filter(pk=owner.team_id).exists()
            ):
                raise serializers.ValidationError({field: 'Related records must belong to a team you lead.'})
            if 70 <= level < 90 and (
                not manager or not owner or not manager.managed_departments.filter(pk=owner.department_id).exists()
            ):
                raise serializers.ValidationError({field: 'Related records must belong to a department you manage.'})

        assigned = attrs.get('assigned_to', getattr(instance, 'assigned_to', None))
        recipient = attrs.get('assigned_to_user', getattr(instance, 'assigned_to_user', None))
        recipient_changed = 'assigned_to_user' in attrs and recipient != getattr(instance, 'assigned_to_user', None)
        if recipient_changed and 'assigned_to' not in attrs:
            new_employee = Employee.objects.filter(
                user=recipient, organization=org, employment_status='active',
            ).first()
            if new_employee:
                assigned = new_employee
                attrs['assigned_to'] = new_employee
                attrs['team'] = new_employee.team
                attrs['department'] = new_employee.department
            else:
                assigned = None
                attrs['assigned_to'] = None
                attrs['team'] = None
                attrs['department'] = None
        if not assigned and not recipient:
            raise serializers.ValidationError({'assigned_to_user': 'Choose a task recipient.'})
        if assigned and recipient and assigned.user_id != recipient.id:
            raise serializers.ValidationError({'assigned_to_user': 'Recipient must match the selected employee.'})
        if assigned and (not instance or assigned != instance.assigned_to) and assigned.employment_status != Employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'assigned_to': 'Tasks can only be assigned to active employees.'})

        team = attrs.get('team', getattr(instance, 'team', None))
        department = attrs.get('department', getattr(instance, 'department', None))
        if assigned and team and assigned.team_id != team.id:
            raise serializers.ValidationError({'team': 'Task team must match the assigned employee team.'})
        if assigned and department and assigned.department_id != department.id:
            raise serializers.ValidationError({'department': 'Task department must match the assigned employee department.'})

        if level < 50 and (
            not employee or (assigned and assigned.id != employee.id) or (recipient and recipient.id != user.id)
        ):
            raise serializers.ValidationError({'assigned_to_user': 'Employees may only create tasks for themselves.'})
        if assigned and 70 <= level < 90 and (
            not manager or not manager.managed_departments.filter(pk=assigned.department_id).exists()
        ):
            raise serializers.ValidationError({'assigned_to': 'Employee must belong to a department you manage.'})
        if assigned and 50 <= level < 70 and (
            not profile or not profile.teams.filter(pk=assigned.team_id).exists()
        ):
            raise serializers.ValidationError({'assigned_to': 'Employee must belong to a team you lead.'})

        if recipient:
            target_employee = Employee.objects.filter(
                user=recipient, organization=org, employment_status='active'
            ).first()
            target_manager = Manager.objects.filter(
                user=recipient, organization=org, employment_status='active'
            ).first()
            target_lead = TeamLead.objects.filter(
                user=recipient, organization=org, employment_status='active'
            ).first()
            if not (target_employee or target_manager or target_lead):
                raise serializers.ValidationError({'assigned_to_user': 'Recipient must be an active staff member in your organization.'})
            if level >= 70 and level < 90:
                departments = manager.managed_departments.all() if manager else []
                in_scope = (
                    target_employee and departments.filter(pk=target_employee.department_id).exists()
                ) or (
                    target_lead and departments.filter(pk=target_lead.department_id).exists()
                )
                if target_manager or not in_scope:
                    raise serializers.ValidationError({'assigned_to_user': 'Choose a team lead or employee in a department you manage.'})
            elif 50 <= level < 70:
                teams = profile.teams.all() if profile else []
                if not target_employee or not teams.filter(pk=target_employee.team_id).exists():
                    raise serializers.ValidationError({'assigned_to_user': 'Choose an employee in a team you lead.'})
            if target_employee and not assigned:
                attrs['assigned_to'] = target_employee

        due_date = attrs.get('due_date')
        if not instance and due_date and due_date.astimezone(organization_timezone(request)).date() < organization_local_date(request):
            raise serializers.ValidationError({'due_date': 'A new task cannot be due before today.'})
        start_date = attrs.get('start_date', getattr(instance, 'start_date', None))
        effective_due_date = due_date or getattr(instance, 'due_date', None)
        if start_date and effective_due_date and start_date > effective_due_date:
            raise serializers.ValidationError({'start_date': 'Task start date must be on or before its due date.'})

        customer = attrs.get('related_customer', getattr(instance, 'related_customer', None))
        lead = attrs.get('related_lead', getattr(instance, 'related_lead', None))
        if lead and customer and lead.customer_id and lead.customer_id != customer.id:
            raise serializers.ValidationError({'related_customer': 'Customer must match the selected lead.'})
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        org = get_user_organization(user, request)
        assigned = validated_data.get('assigned_to')
        if assigned:
            validated_data.setdefault('team', assigned.team)
            validated_data.setdefault('department', assigned.department)
            validated_data.setdefault('assigned_to_user', assigned.user)
        manager_qs = getattr(user, 'manager_set', None)
        manager = manager_qs.first() if manager_qs and manager_qs.exists() else None
        teamlead_qs = getattr(user, 'teamlead_profiles', None)
        teamlead = teamlead_qs.first() if teamlead_qs and teamlead_qs.exists() else None
        level = get_user_role_context(user, request)['hierarchy_level']
        if level >= 70 and manager:
            validated_data['assigned_by_manager'] = manager
        if level == 50 and teamlead:
            validated_data['assigned_by_teamlead'] = teamlead
        with transaction.atomic():
            task = super().create({**validated_data, 'organization': org, 'assigned_by_user': user})
            TaskHistory.objects.create(
                task=task, previous_status=task.status, new_status=task.status,
                changed_by=user, comment='Task created',
            )
        return task

    def update(self, instance, validated_data):
        changed_fields = [name for name, value in validated_data.items() if getattr(instance, name) != value]
        with transaction.atomic():
            task = super().update(instance, validated_data)
            if changed_fields:
                TaskHistory.objects.create(
                    task=task, previous_status=instance.status, new_status=task.status,
                    changed_by=self.context['request'].user,
                    comment='Task updated: ' + ', '.join(changed_fields),
                )
        return task


class CustomerFollowUpSerializer(serializers.ModelSerializer):
    scheduled_at = OrganizationDateTimeField()
    title = serializers.CharField(required=True, allow_blank=False)
    contact_name = serializers.SerializerMethodField()
    contact_phone = serializers.SerializerMethodField()
    contact_email = serializers.SerializerMethodField()
    contact_record_code = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = CostomerFollowUp
        fields = '__all__'
        read_only_fields = (
            'organization', 'created_by', 'created_by_user', 'created_at',
            'updated_at', 'completed_at',
        )

    def _related_record(self, obj):
        if self.Meta.model is CostomerFollowUp:
            return obj.customer
        return obj.lead

    def _contact_customer(self, obj):
        return obj.customer if self.Meta.model is CostomerFollowUp else None

    def get_contact_name(self, obj):
        record = self._related_record(obj)
        customer = self._contact_customer(obj)
        return getattr(record, 'contact_name', '') or getattr(customer, 'full_name', '') or getattr(customer, 'legal_name', '') or 'Customer'

    def get_contact_phone(self, obj):
        record = self._related_record(obj)
        customer = self._contact_customer(obj)
        return getattr(record, 'phone', '') or getattr(customer, 'primary_phone', '') or ''

    def get_contact_email(self, obj):
        record = self._related_record(obj)
        customer = self._contact_customer(obj)
        return getattr(record, 'email', '') or getattr(customer, 'email', '') or ''

    def get_contact_record_code(self, obj):
        record = self._related_record(obj)
        return getattr(record, 'lead_code', '') or getattr(record, 'customer_code', '') or ''

    def get_created_by_name(self, obj):
        user = getattr(getattr(obj, 'created_by', None), 'user', None) or getattr(obj, 'created_by_user', None)
        return (user.get_full_name() or user.username) if user else ''

    def get_assigned_to_name(self, obj):
        user = getattr(getattr(obj, 'assigned_to', None), 'user', None)
        return (user.get_full_name() or user.username) if user else ''

    def validate(self, attrs):
        request = self.context['request']
        user = request.user
        org = get_user_organization(user, request)
        instance = self.instance
        relation_name = 'customer' if self.Meta.model is CostomerFollowUp else 'lead'
        target = attrs.get(relation_name, getattr(instance, relation_name, None))
        if not org or not target or target.organization_id != org.id:
            raise serializers.ValidationError({relation_name: 'Choose a record in your organization.'})
        level = get_user_role_context(user, request)['hierarchy_level']
        employee = getattr(user, 'employee', None)
        if level < 30:
            raise serializers.ValidationError('Only organization staff can create or update internal follow-ups.')

        assigned = attrs.get('assigned_to', getattr(instance, 'assigned_to', None))
        if not assigned and not instance and employee:
            assigned = employee
            attrs['assigned_to'] = employee
        if not assigned:
            raise serializers.ValidationError({'assigned_to': 'Assign this follow-up to an employee.'})
        if assigned.organization_id != org.id:
            raise serializers.ValidationError({'assigned_to': 'Employee must belong to your organization.'})
        if (not instance or assigned != instance.assigned_to) and assigned.employment_status != Employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'assigned_to': 'Assign follow-ups only to active employees.'})

        owner = getattr(target, 'assigned_to', None)
        if level < 50 and (not employee or assigned != employee or (not instance and owner != employee)):
            raise serializers.ValidationError({relation_name: 'Employees can only manage follow-ups for their own assigned records.'})
        if 50 <= level < 70:
            profile = user.teamlead_profiles.first() if hasattr(user, 'teamlead_profiles') else None
            if (
                not profile or not owner or not profile.teams.filter(pk=owner.team_id).exists()
                or not profile.teams.filter(pk=assigned.team_id).exists()
            ):
                raise serializers.ValidationError({'assigned_to': 'Record and assigned employee must be in a team you lead.'})
        if 70 <= level < 90:
            manager = user.manager_set.first() if hasattr(user, 'manager_set') else None
            if (
                not manager or not owner or not manager.managed_departments.filter(pk=owner.department_id).exists()
                or not manager.managed_departments.filter(pk=assigned.department_id).exists()
            ):
                raise serializers.ValidationError({'assigned_to': 'Record and assigned employee must be in a department you manage.'})

        duration = attrs.get('meeting_duration_minutes', getattr(instance, 'meeting_duration_minutes', 30))
        if duration < 1 or duration > 720:
            raise serializers.ValidationError({'meeting_duration_minutes': 'Meeting duration must be between 1 and 720 minutes.'})
        raw_emails = attrs.get('invitee_emails', getattr(instance, 'invitee_emails', ''))
        email_field = serializers.EmailField()
        for email in filter(None, (item.strip() for item in raw_emails.split(','))):
            try:
                email_field.run_validation(email)
            except serializers.ValidationError:
                raise serializers.ValidationError({'invitee_emails': f'Invalid invitee email: {email}'})

        new_status = attrs.get('status', getattr(instance, 'status', None))
        if not instance and new_status not in (None, 'PENDING'):
            raise serializers.ValidationError({'status': 'New follow-ups must start as pending.'})
        if instance and new_status == 'COMPLETED' and instance.status != 'COMPLETED':
            outcome = attrs.get('outcome', instance.outcome)
            if not outcome or not outcome.strip():
                raise serializers.ValidationError({'outcome': 'Enter the follow-up outcome before marking it complete.'})
        scheduled = attrs.get('scheduled_at')
        if scheduled and (not instance or scheduled != instance.scheduled_at) and scheduled < timezone.now():
            raise serializers.ValidationError({'scheduled_at': 'Schedule a new or rescheduled follow-up for the present or a future time.'})
        if instance and new_status != instance.status and (instance.status != 'PENDING' or new_status not in ('COMPLETED', 'CANCELLED')):
            raise serializers.ValidationError({'status': 'Follow-ups can only move from pending to completed or cancelled.'})
        return attrs

    def update(self, instance, data):
        if data.get('status') in ('COMPLETED', 'CANCELLED') and instance.status == 'PENDING':
            data['completed_at'] = timezone.now()
        return super().update(instance, data)

    def create(self, data):
        request = self.context['request']
        employee = getattr(request.user, 'employee', None)
        data.setdefault('assigned_to', employee)
        return super().create({
            **data,
            'organization': get_user_organization(request.user, request),
            'created_by': employee,
            'created_by_user': request.user,
        })


class LeadFollowUpSerializer(CustomerFollowUpSerializer):
    class Meta(CustomerFollowUpSerializer.Meta):
        model = LeadFollowUp
