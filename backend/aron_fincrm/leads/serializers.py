import uuid
from django.db import transaction
from rest_framework import serializers
from leads.models import Lead, LeadAssignmentHistory, LeadStatusHistory
from employes.models import Employee
from organizations.tenant import get_user_organization, get_user_role_context


class LeadAssignmentHistorySerializer(serializers.ModelSerializer):
    old_owner_name = serializers.SerializerMethodField(read_only=True)
    new_owner_name = serializers.SerializerMethodField(read_only=True)
    assigned_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeadAssignmentHistory
        fields = [
            'id',
            'lead',
            'old_owner',
            'old_owner_name',
            'new_owner',
            'new_owner_name',
            'assigned_by',
            'assigned_by_name',
            'reason',
            'assigned_at',
        ]
        read_only_fields = ['id', 'assigned_at']

    def get_old_owner_name(self, obj):
        if obj.old_owner and obj.old_owner.user:
            return obj.old_owner.user.get_full_name() or obj.old_owner.user.username
        return None

    def get_new_owner_name(self, obj):
        if obj.new_owner and obj.new_owner.user:
            return obj.new_owner.user.get_full_name() or obj.new_owner.user.username
        return None

    def get_assigned_by_name(self, obj):
        if obj.assigned_by:
            return obj.assigned_by.get_full_name() or obj.assigned_by.username
        return None


class LeadStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name=serializers.SerializerMethodField()
    class Meta:
        model=LeadStatusHistory
        fields=['id','old_status','new_status','changed_by_name','notes','changed_at']
    def get_changed_by_name(self,obj): return obj.changed_by.get_full_name() or obj.changed_by.username


class LeadSerializer(serializers.ModelSerializer):
    lead_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    assignment_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)
    assigned_to_name = serializers.SerializerMethodField(read_only=True)
    address = serializers.SerializerMethodField(read_only=True)
    portal_username = serializers.CharField(source='portal_user.username', read_only=True, allow_null=True)
    has_portal_account = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    customer_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            'id',
            'lead_code',
            'contact_name',
            'phone',
            'email',
            'city',
            'state',
            'address',
            'source',
            'priority',
            'status',
            'expected_amount',
            'currency',
            'assigned_to',
            'assigned_to_name',
            'assignment_reason',
            'portal_username', 'has_portal_account',
            'customer', 'customer_name', 'requested_amount', 'approved_amount', 'disbursed_amount',
            'upfront_deductions_amount', 'net_disbursed_amount', 'annual_interest_rate',
            'interest_calculation_method', 'loan_tenure_months', 'monthly_repayment_amount',
            'next_payment_due_date', 'disbursed_at', 'completed_at',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'customer', 'customer_name', 'status', 'portal_username', 'has_portal_account', 'created_at', 'updated_at', 'approved_amount', 'disbursed_amount', 'upfront_deductions_amount', 'net_disbursed_amount', 'annual_interest_rate', 'interest_calculation_method', 'loan_tenure_months', 'monthly_repayment_amount', 'next_payment_due_date', 'disbursed_at', 'completed_at']

    def validate(self,attrs):
        req=self.context['request']; user=req.user
        org=get_user_organization(user,req)
        if not self.instance and org:
            from subscriptions.entitlements import enforce_resource_limit
            enforce_resource_limit(org, 'leads')
        assigned=attrs.get('assigned_to')
        if assigned and (not org or assigned.organization_id!=org.id):
            raise serializers.ValidationError({'assigned_to':'Employee must belong to your organization.'})
        if assigned and assigned.employment_status != Employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'assigned_to':'Assign leads only to active employees.'})
        role=get_user_role_context(user,req); level=role['hierarchy_level']
        if not self.instance and 50<=level<90 and not attrs.get('assigned_to'):
            raise serializers.ValidationError({'assigned_to':'Assign the lead to an employee in your reporting scope.'})
        assigned_people=[assigned] if assigned else []
        if level>=70 and level<90:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            depts=manager.managed_departments.all() if manager else []
            if any(person.department_id not in set(depts.values_list('id',flat=True)) for person in assigned_people):
                raise serializers.ValidationError({'assigned_to':'Lead staff must belong to departments you manage.'})
        elif level>=50 and level<70:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            teams=profile.teams.all() if profile else []
            if any(person.team_id not in set(teams.values_list('id',flat=True)) for person in assigned_people):
                raise serializers.ValidationError({'assigned_to':'Lead staff must belong to teams you lead.'})
        elif level<50:
            employee=getattr(user,'employee',None)
            if attrs.get('assigned_to') and (not employee or attrs['assigned_to'].id!=employee.id):
                raise serializers.ValidationError({'assigned_to':'Employees may only assign the lead owner to themselves.'})
        return attrs

    def get_assigned_to_name(self, obj):
        if obj.assigned_to and obj.assigned_to.user:
            return obj.assigned_to.user.get_full_name() or obj.assigned_to.user.username
        return None

    def get_address(self, obj):
        return ', '.join(part for part in (obj.city, obj.state) if part)

    def get_has_portal_account(self,obj): return bool(obj.portal_user_id)

    def get_customer_name(self, obj):
        return (obj.customer.full_name or obj.customer.legal_name) if obj.customer_id else ''

    def get_created_by_name(self, obj):
        if obj.created_by and obj.created_by.user:
            return obj.created_by.user.get_full_name() or obj.created_by.user.username
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        org = get_user_organization(user, request)

        if not validated_data.get('lead_code'):
            validated_data['lead_code'] = f"LEAD-{uuid.uuid4().hex[:8].upper()}"

        validated_data['organization'] = org

        # Link creator employee profile if available
        creator_emp = getattr(user, 'employee', None)
        if creator_emp:
            validated_data['created_by'] = creator_emp

        # If assigned_to is not specified and creator is an employee, auto-assign to creator
        if not validated_data.get('assigned_to') and creator_emp:
            validated_data['assigned_to'] = creator_emp

        with transaction.atomic():
            lead=super().create(validated_data)
            return lead

    def update(self, instance, validated_data):
        assignment_reason = validated_data.pop('assignment_reason', '').strip()
        old_owner = instance.assigned_to
        old_owner_id = instance.assigned_to_id
        with transaction.atomic():
            lead = super().update(instance, validated_data)
            if lead.assigned_to_id != old_owner_id:
                request = self.context.get('request')
                assigned_name = ''
                if lead.assigned_to and lead.assigned_to.user:
                    assigned_name = lead.assigned_to.user.get_full_name() or lead.assigned_to.user.username
                LeadAssignmentHistory.objects.create(
                    lead=lead,
                    old_owner=old_owner,
                    new_owner=lead.assigned_to,
                    assigned_by=request.user,
                    reason=assignment_reason or (f'Assigned to {assigned_name}' if assigned_name else 'Lead assignment changed'),
                )
        return lead


class LeadPortalSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = ['id', 'lead_code', 'contact_name', 'phone', 'email', 'customer_name', 'status', 'expected_amount', 'currency', 'created_at']
        read_only_fields = fields

    def get_customer_name(self, obj):
        return (obj.customer.full_name or obj.customer.legal_name) if obj.customer_id else obj.contact_name


class LeadAssignSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        request = self.context.get('request')
        org = get_user_organization(request.user, request)
        value=attrs.get('employee_id')
        if value:
            emp=Employee.objects.filter(id=value,organization=org).first()
            if not emp: raise serializers.ValidationError({'employee_id':'Staff member not found in your organization.'})
            if emp.employment_status != Employee.EmploymentStatus.ACTIVE:
                raise serializers.ValidationError({'employee_id':'Assign leads only to active employees.'})
            ctx=get_user_role_context(request.user,request)
            if 70<=ctx['hierarchy_level']<90:
                manager=request.user.manager_set.first()
                if not manager or not manager.managed_departments.filter(pk=emp.department_id).exists(): raise serializers.ValidationError({'employee_id':'Choose an employee in a department you manage.'})
            elif 50<=ctx['hierarchy_level']<70:
                profile=request.user.teamlead_profiles.first()
                if not profile or not profile.teams.filter(pk=emp.team_id).exists(): raise serializers.ValidationError({'employee_id':'Choose an employee in a team you lead.'})
        if not value:
            raise serializers.ValidationError('Select at least one staff assignment.')
        return attrs
