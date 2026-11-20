import uuid
from django.db import transaction
from rest_framework import serializers
from customers.models import Customer, CustomerTag, CustomerAssignmentHistory
from organizations.tenant import get_user_organization
from organizations.tenant import get_user_role_context


class CustomerTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerTag
        fields = ['id', 'tag']


class CustomerAssignmentHistorySerializer(serializers.ModelSerializer):
    previous_owner_name = serializers.SerializerMethodField()
    new_owner_name = serializers.SerializerMethodField()
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomerAssignmentHistory
        fields = ['id', 'previous_owner_name', 'new_owner_name', 'changed_by_name', 'reason', 'changed_at']

    def get_previous_owner_name(self, obj):
        return self._employee_name(obj.previous_owner)

    def get_new_owner_name(self, obj):
        return self._employee_name(obj.new_owner)

    def get_changed_by_name(self, obj):
        return obj.changed_by.get_full_name() or obj.changed_by.username

    @staticmethod
    def _employee_name(employee):
        if not employee or not employee.user:
            return None
        return employee.user.get_full_name() or employee.user.username


class CustomerSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=Customer.Status.choices,
        required=False,
        default=Customer.Status.PROSPECT,
    )
    customer_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    tags = serializers.SerializerMethodField(read_only=True)
    tag_list = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
    )
    created_by_name = serializers.SerializerMethodField(read_only=True)
    assigned_to_name = serializers.SerializerMethodField(read_only=True)
    change_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Customer
        fields = [
            'id',
            'customer_code',
            'customer_type',
            'full_name',
            'legal_name',
            'primary_phone',
            'email',
            'alternate_phone',
            'preferred_channel',
            'address_line1',
            'address_line2',
            'city',
            'state',
            'pin_code',
            'country',
            'business_category',
            'segment',
            'source',
            'status',
            'priority',
            'notes',
            'tags',
            'tag_list',
            'created_by',
            'assigned_to',
            'assigned_to_name',
            'change_reason',
            'created_by_name',
            'created_at',
            'updated_at',
            'archived_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'archived_at']

    def get_tags(self, obj):
        return list(obj.tags.values_list('tag', flat=True))

    def get_created_by_name(self, obj):
        if obj.created_by and obj.created_by.user:
            return obj.created_by.user.get_full_name() or obj.created_by.user.username
        return None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to and obj.assigned_to.user:
            return obj.assigned_to.user.get_full_name() or obj.assigned_to.user.username
        return None

    def validate(self,attrs):
        request=self.context['request']; user=request.user
        org=get_user_organization(user,request)
        if not org: raise serializers.ValidationError('An active organization is required.')
        if attrs.get('customer_type')==Customer.CustomerType.INDIVIDUAL and not (attrs.get('full_name') or getattr(self.instance,'full_name','')):
            raise serializers.ValidationError({'full_name':'Full name is required for an individual customer.'})
        if attrs.get('customer_type')==Customer.CustomerType.BUSINESS and not (attrs.get('legal_name') or attrs.get('full_name') or getattr(self.instance,'legal_name','')):
            raise serializers.ValidationError({'legal_name':'Business legal name is required.'})
        assigned=attrs.get('assigned_to',getattr(self.instance,'assigned_to',None))
        if assigned and (not org or assigned.organization_id!=org.id): raise serializers.ValidationError({'assigned_to':'Employee must belong to your organization.'})
        if assigned and (not self.instance or assigned != self.instance.assigned_to) and assigned.employment_status != assigned.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'assigned_to':'Assign customers only to active employees.'})
        ctx=get_user_role_context(user,request); level=ctx['hierarchy_level']
        if level>=70 and level<90 and assigned:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            if not manager or not manager.managed_departments.filter(pk=assigned.department_id).exists(): raise serializers.ValidationError({'assigned_to':'Customer must be assigned within a department you manage.'})
        elif level>=50 and level<70 and assigned:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            if not profile or not profile.teams.filter(pk=assigned.team_id).exists(): raise serializers.ValidationError({'assigned_to':'Customer must be assigned within a team you lead.'})
        elif level<50 and assigned and getattr(user,'employee',None) and assigned.pk!=user.employee.pk and (not self.instance or assigned.pk!=self.instance.assigned_to_id):
            raise serializers.ValidationError({'assigned_to':'Employees can only assign customers to themselves.'})
        if not self.instance and level>=50 and level<90 and not assigned:
            raise serializers.ValidationError({'assigned_to':'Assign the customer to an employee in your reporting scope.'})
        return attrs

    def validate_tag_list(self,value):
        allowed={choice for choice,_ in CustomerTag.Tag.choices}
        invalid=[tag for tag in value if tag not in allowed]
        if invalid: raise serializers.ValidationError(f'Unsupported tags: {", ".join(invalid)}')
        return value

    def create(self, validated_data):
        tag_list = validated_data.pop('tag_list', [])
        change_reason = validated_data.pop('change_reason', '')
        request = self.context.get('request')
        user = request.user
        org = get_user_organization(user, request)

        if not validated_data.get('customer_code'):
            validated_data['customer_code'] = f"CUST-{uuid.uuid4().hex[:8].upper()}"

        validated_data['organization'] = org

        creator_emp = getattr(user, 'employee', None)
        if creator_emp:
            validated_data['created_by'] = creator_emp
            validated_data.setdefault('assigned_to',creator_emp)

        with transaction.atomic():
            customer = super().create(validated_data)
            if customer.assigned_to_id:
                CustomerAssignmentHistory.objects.create(
                    customer=customer,
                    new_owner=customer.assigned_to,
                    changed_by=user,
                    reason=change_reason or 'Initial customer assignment',
                )
            for t in tag_list:
                CustomerTag.objects.create(customer=customer, tag=t)
            return customer

    def update(self, instance, validated_data):
        tag_list = validated_data.pop('tag_list', None)
        change_reason = validated_data.pop('change_reason', '')
        previous_owner = instance.assigned_to
        with transaction.atomic():
            customer = super().update(instance, validated_data)
            if previous_owner != customer.assigned_to:
                CustomerAssignmentHistory.objects.create(
                    customer=customer,
                    previous_owner=previous_owner,
                    new_owner=customer.assigned_to,
                    changed_by=self.context['request'].user,
                    reason=change_reason or 'Customer assignment changed',
                )
            if tag_list is not None:
                customer.tags.all().delete()
                for t in tag_list:
                    CustomerTag.objects.create(customer=customer, tag=t)
            return customer
