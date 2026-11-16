import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from leads.models import Lead, LeadAssignmentHistory, LeadStatusHistory
from employes.models import Employee
from customers.models import Customer, CustomerTag
from organizations.tenant import get_user_organization, get_user_role_context


class LeadAssignmentHistorySerializer(serializers.ModelSerializer):
    old_owner_name = serializers.SerializerMethodField(read_only=True)
    new_owner_name = serializers.SerializerMethodField(read_only=True)
    assigned_by_name = serializers.SerializerMethodField(read_only=True)
    new_doc_officer_name = serializers.SerializerMethodField(read_only=True)
    new_sales_analyst_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeadAssignmentHistory
        fields = [
            'id',
            'lead',
            'old_owner',
            'old_owner_name',
            'new_owner',
            'new_owner_name',
            'old_doc_officer', 'new_doc_officer', 'new_doc_officer_name',
            'old_sales_analyst', 'new_sales_analyst', 'new_sales_analyst_name',
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

    def get_new_doc_officer_name(self, obj):
        return obj.new_doc_officer.user.get_full_name() or obj.new_doc_officer.user.username if obj.new_doc_officer_id else None

    def get_new_sales_analyst_name(self, obj):
        return obj.new_sales_analyst.user.get_full_name() or obj.new_sales_analyst.user.username if obj.new_sales_analyst_id else None


class LeadStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name=serializers.SerializerMethodField()
    class Meta:
        model=LeadStatusHistory
        fields=['id','old_status','new_status','changed_by_name','notes','changed_at']
    def get_changed_by_name(self,obj): return obj.changed_by.get_full_name() or obj.changed_by.username


class LeadSerializer(serializers.ModelSerializer):
    lead_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    assigned_to_name = serializers.SerializerMethodField(read_only=True)
    assigned_doc_officer_name = serializers.SerializerMethodField(read_only=True)
    assigned_sales_analyst_name = serializers.SerializerMethodField(read_only=True)
    portal_username = serializers.CharField(source='portal_user.username', read_only=True, allow_null=True)
    has_portal_account = serializers.SerializerMethodField(read_only=True)
    create_portal_account = serializers.BooleanField(write_only=True, required=False, default=True)
    portal_password = serializers.CharField(write_only=True, required=False, allow_blank=False, min_length=8)
    portal_login = serializers.CharField(write_only=True, required=False, allow_blank=False)
    created_by_name = serializers.SerializerMethodField(read_only=True)

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
            'source',
            'priority',
            'status',
            'expected_amount',
            'currency',
            'assigned_to',
            'assigned_to_name',
            'assigned_doc_officer',
            'assigned_doc_officer_name',
            'assigned_sales_analyst',
            'assigned_sales_analyst_name',
            'portal_username', 'has_portal_account', 'create_portal_account', 'portal_login', 'portal_password',
            'converted_customer',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'converted_customer', 'status', 'portal_username', 'has_portal_account', 'created_at', 'updated_at']

    def validate(self,attrs):
        req=self.context['request']; user=req.user
        org=get_user_organization(user,req)
        for field in ('assigned_to','assigned_doc_officer','assigned_sales_analyst'):
            assigned=attrs.get(field)
            if assigned and (not org or assigned.organization_id!=org.id):
                raise serializers.ValidationError({field:'Employee must belong to your organization.'})
            required_role={'assigned_doc_officer':{'doc_officer','document_verification_officer'},'assigned_sales_analyst':{'sales_analyst'}}.get(field)
            if assigned and required_role:
                codes={assigned.role.code} if assigned.role_id else set()
                codes.update(assigned.additional_roles.values_list('code',flat=True))
                if not codes.intersection(required_role):
                    raise serializers.ValidationError({field:'The selected staff member does not have the required role.'})
        role=get_user_role_context(user,req); level=role['hierarchy_level']
        if not self.instance and 50<=level<90 and not attrs.get('assigned_to'):
            raise serializers.ValidationError({'assigned_to':'Assign the lead to an employee in your reporting scope.'})
        assigned_people=[attrs.get(field) for field in ('assigned_to','assigned_doc_officer','assigned_sales_analyst') if attrs.get(field)]
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
            if any(person.team_id != employee.team_id for field in ('assigned_doc_officer','assigned_sales_analyst') if (person:=attrs.get(field)) and employee and person.id!=employee.id):
                raise serializers.ValidationError({'assigned_doc_officer':'Supporting staff must be in your team.'})
        if self.instance and any(field in attrs for field in ('assigned_to','assigned_doc_officer','assigned_sales_analyst')):
            raise serializers.ValidationError('Use the Assign lead action to change staff assignments so assignment history is retained.')
        if attrs.get('create_portal_account'):
            login=attrs.get('portal_login')
            password=attrs.get('portal_password')
            User=get_user_model()
            if not login or not password:
                raise serializers.ValidationError({'portal_login':'Set a login username and password to create a lead portal account.'})
            if User.objects.filter(username__iexact=login).exists():
                raise serializers.ValidationError({'portal_login':'This username is already in use.'})
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try: validate_password(password)
            except ValidationError as error: raise serializers.ValidationError({'portal_password':list(error.messages)})
        elif attrs.get('portal_login') or attrs.get('portal_password'):
            raise serializers.ValidationError({'create_portal_account':'Enable lead portal account creation first.'})
        return attrs

    def get_assigned_to_name(self, obj):
        if obj.assigned_to and obj.assigned_to.user:
            return obj.assigned_to.user.get_full_name() or obj.assigned_to.user.username
        return None

    def get_assigned_doc_officer_name(self,obj):
        return obj.assigned_doc_officer.user.get_full_name() or obj.assigned_doc_officer.user.username if obj.assigned_doc_officer_id else None

    def get_assigned_sales_analyst_name(self,obj):
        return obj.assigned_sales_analyst.user.get_full_name() or obj.assigned_sales_analyst.user.username if obj.assigned_sales_analyst_id else None

    def get_has_portal_account(self,obj): return bool(obj.portal_user_id)

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

        create_portal=validated_data.pop('create_portal_account',False)
        portal_login=validated_data.pop('portal_login',None)
        portal_password=validated_data.pop('portal_password',None)

        # Link creator employee profile if available
        creator_emp = getattr(user, 'employee', None)
        if creator_emp:
            validated_data['created_by'] = creator_emp

        # If assigned_to is not specified and creator is an employee, auto-assign to creator
        if not validated_data.get('assigned_to') and creator_emp:
            validated_data['assigned_to'] = creator_emp
        active_role=get_user_role_context(user,request)['role_code']
        if active_role=='sales_analyst' and creator_emp and not validated_data.get('assigned_sales_analyst'):
            validated_data['assigned_sales_analyst']=creator_emp
        if active_role in ('doc_officer','document_verification_officer') and creator_emp and not validated_data.get('assigned_doc_officer'):
            validated_data['assigned_doc_officer']=creator_emp

        User=get_user_model()
        with transaction.atomic():
            lead=super().create(validated_data)
            if create_portal:
                lead.portal_user=User.objects.create_user(username=portal_login,email=lead.email, password=portal_password,first_name=lead.contact_name,default_organization=org)
                lead.portal_user.save(update_fields=['username'])
                lead.save(update_fields=['portal_user'])
            return lead


class LeadAssignSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField(required=False, allow_null=True)
    document_officer_id = serializers.UUIDField(required=False, allow_null=True)
    sales_analyst_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        request = self.context.get('request')
        org = get_user_organization(request.user, request)
        checks=(('employee_id',None),('document_officer_id',{'doc_officer','document_verification_officer'}),('sales_analyst_id',{'sales_analyst'}))
        for field,roles in checks:
            value=attrs.get(field)
            if not value: continue
            emp=Employee.objects.filter(id=value,organization=org).select_related('role').first()
            if not emp: raise serializers.ValidationError({field:'Staff member not found in your organization.'})
            if roles:
                codes={emp.role.code} if emp.role_id else set(); codes.update(emp.additional_roles.values_list('code',flat=True))
                if not codes.intersection(roles): raise serializers.ValidationError({field:'The selected staff member does not have the required role.'})
        if not any(attrs.get(key) for key in ('employee_id','document_officer_id','sales_analyst_id')):
            raise serializers.ValidationError('Select at least one staff assignment.')
        return attrs


class LeadConvertSerializer(serializers.Serializer):
    customer_type = serializers.ChoiceField(
        choices=Customer.CustomerType.choices,
        default=Customer.CustomerType.INDIVIDUAL
    )
    legal_name = serializers.CharField(required=False, allow_blank=True, default="")
    address_line1 = serializers.CharField(required=False, allow_blank=True, default="")
    address_line2 = serializers.CharField(required=False, allow_blank=True, default="")
    city = serializers.CharField(required=False, allow_blank=True, default="")
    state = serializers.CharField(required=False, allow_blank=True, default="")
    pin_code = serializers.CharField(required=False, allow_blank=True, default="")
    business_category = serializers.CharField(required=False, allow_blank=True, default="")
    segment = serializers.CharField(required=False, allow_blank=True, default="Retail")
    tag = serializers.ChoiceField(
        choices=CustomerTag.Tag.choices,
        required=False,
        default=CustomerTag.Tag.GENERAL
    )
