from django.utils import timezone
from rest_framework import serializers
from communications.models import Interaction, InteractionAttendee, MessageDraft
from organizations.tenant import get_user_organization, get_user_role_context


class InteractionAttendeeSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = InteractionAttendee
        fields = ['id', 'interaction', 'employee', 'employee_name', 'external_name', 'external_email']
        read_only_fields=['id','employee_name']

    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        interaction=attrs.get('interaction',getattr(instance,'interaction',None)); employee=attrs.get('employee',getattr(instance,'employee',None))
        if not org or not interaction or interaction.organization_id!=org.id: raise serializers.ValidationError({'interaction':'Interaction must belong to your organization.'})
        if employee and employee.organization_id!=org.id: raise serializers.ValidationError({'employee':'Employee must belong to your organization.'})
        if not employee and not (attrs.get('external_name') or getattr(instance,'external_name','')): raise serializers.ValidationError({'external_name':'Add an employee or external attendee name.'})
        return attrs

    def get_employee_name(self, obj):
        if obj.employee and obj.employee.user:
            return obj.employee.user.get_full_name() or obj.employee.user.username
        return None


class InteractionSerializer(serializers.ModelSerializer):
    occurred_at = serializers.DateTimeField(required=False, default=timezone.now)
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    lead_name = serializers.CharField(source='lead.contact_name', read_only=True)
    employee_name = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)
    attendees = InteractionAttendeeSerializer(source='interactionattendee_set', many=True, read_only=True)

    class Meta:
        model = Interaction
        fields = [
            'id',
            'customer',
            'customer_name',
            'lead',
            'lead_name',
            'application',
            'employee',
            'employee_name',
            'interaction_type',
            'direction',
            'subject',
            'content',
            'duration',
            'outcome',
            'status',
            'occurred_at',
            'next_action',
            'external_reference',
            'attendees',
            'created_by_name',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by_name', 'created_at']

    def get_employee_name(self, obj):
        if obj.employee and obj.employee.user:
            return obj.employee.user.get_full_name() or obj.employee.user.username
        return None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        checks=(('customer',attrs.get('customer',getattr(instance,'customer',None))),('lead',attrs.get('lead',getattr(instance,'lead',None))),('application',attrs.get('application',getattr(instance,'application',None))),('employee',attrs.get('employee',getattr(instance,'employee',None))))
        for field,obj in checks:
            if obj and (not org or obj.organization_id!=org.id): raise serializers.ValidationError({field:'Choose a record in your organization.'})
        app=attrs.get('application',getattr(instance,'application',None)); customer=attrs.get('customer',getattr(instance,'customer',None))
        if app and customer and app.customer_id!=customer.id: raise serializers.ValidationError({'customer':'Customer must match the application customer.'})
        if not any((attrs.get(key,getattr(instance,key,None)) for key in ('customer','lead','application'))):
            raise serializers.ValidationError('Link the interaction to a customer, lead, or application.')
        role=get_user_role_context(req.user,req); level=role['hierarchy_level']; employee=getattr(req.user,'employee',None)
        for key,target in (('customer',attrs.get('customer',getattr(instance,'customer',None))),('lead',attrs.get('lead',getattr(instance,'lead',None))),('application',app)):
            if not target: continue
            owner=target.assigned_to if key in ('customer','lead') else target.assigned_employee
            if level<50 and (not employee or owner!=employee): raise serializers.ValidationError({key:'This record must be assigned to you.'})
            if 50<=level<70:
                profile=req.user.teamlead_profiles.first() if hasattr(req.user,'teamlead_profiles') else None
                if not profile or not owner or not profile.teams.filter(pk=owner.team_id).exists(): raise serializers.ValidationError({key:'This record must belong to a team you lead.'})
            if 70<=level<90:
                manager=req.user.manager_set.first() if hasattr(req.user,'manager_set') else None
                if not manager or not owner or not manager.managed_departments.filter(pk=owner.department_id).exists(): raise serializers.ValidationError({key:'This record must belong to a department you manage.'})
        performer=attrs.get('employee',getattr(instance,'employee',None))
        if performer and performer.organization_id!=org.id: raise serializers.ValidationError({'employee':'Employee must belong to your organization.'})
        if level<50 and performer and performer!=employee: raise serializers.ValidationError({'employee':'Employees may only record their own interactions.'})
        if not performer and employee: attrs['employee']=employee
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        org = get_user_organization(user, request)

        validated_data['organization'] = org
        validated_data['created_by'] = user

        if not validated_data.get('employee'):
            creator_emp = getattr(user, 'employee', None)
            if creator_emp:
                validated_data['employee'] = creator_emp

        if not validated_data.get('occurred_at'):
            validated_data['occurred_at'] = timezone.now()

        return super().create(validated_data)


class MessageDraftSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MessageDraft
        fields = [
            'id',
            'customer',
            'customer_name',
            'channel',
            'subject',
            'message',
            'status',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'status', 'created_by_name', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def validate_customer(self,customer):
        org=get_user_organization(self.context['request'].user,self.context['request'])
        if not org or customer.organization_id!=org.id: raise serializers.ValidationError('Customer must belong to your organization.')
        return customer

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        org = get_user_organization(user, request)

        validated_data['organization'] = org
        validated_data['created_by'] = user
        if not validated_data.get('status'):
            validated_data['status'] = MessageDraft.Status.DRAFT

        return super().create(validated_data)
