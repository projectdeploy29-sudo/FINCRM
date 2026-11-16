from django.utils import timezone
from rest_framework import serializers
from communications.models import Interaction, InteractionAttendee, MessageDraft
from organizations.tenant import get_user_organization


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
