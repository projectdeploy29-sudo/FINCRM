from rest_framework import serializers
from applications.models import FinancialApplication, ApplicationStatusHistory, ApplicationChecklist
from organizations.tenant import get_user_organization, get_user_role_context

class FinancialApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialApplication
        fields = '__all__'
        read_only_fields = ('organization', 'created_by', 'status', 'approved_amount', 'disbursed_amount', 'submitted_at', 'completed_at', 'created_at', 'updated_at')
    def validate_customer(self, customer):
        org=get_user_organization(self.context['request'].user, self.context['request'])
        if not org or customer.organization_id != org.id:
            raise serializers.ValidationError('Customer must belong to your organization.')
        return customer
    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        lead=attrs.get('lead',getattr(instance,'lead',None)); employee=attrs.get('assigned_employee',getattr(instance,'assigned_employee',None))
        if lead and (not org or lead.organization_id!=org.id): raise serializers.ValidationError({'lead':'Lead must belong to your organization.'})
        if employee and (not org or employee.organization_id!=org.id): raise serializers.ValidationError({'assigned_employee':'Employee must belong to your organization.'})
        role=get_user_role_context(req.user,req); level=role['hierarchy_level']; user=req.user
        if not instance and 50<=level<90 and not employee:
            raise serializers.ValidationError({'assigned_employee':'Assign the application to an employee in your reporting scope.'})
        if employee and 70<=level<90:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            if not manager or not manager.managed_departments.filter(pk=employee.department_id).exists(): raise serializers.ValidationError({'assigned_employee':'Employee must belong to a department you manage.'})
        elif employee and 50<=level<70:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            if not profile or not profile.teams.filter(pk=employee.team_id).exists(): raise serializers.ValidationError({'assigned_employee':'Employee must belong to a team you lead.'})
        elif employee and level<50:
            own=getattr(user,'employee',None)
            if not own or employee.pk!=own.pk: raise serializers.ValidationError({'assigned_employee':'Employees may only assign applications to themselves.'})
        customer=attrs.get('customer',getattr(instance,'customer',None))
        if customer and lead and lead.converted_customer_id and lead.converted_customer_id!=customer.id:
            raise serializers.ValidationError({'lead':'The application customer must match the lead’s converted customer.'})
        if not instance and org:
            from subscriptions.models import Subscription
            from django.utils import timezone
            subscription=Subscription.objects.filter(organization=org,status__in=['active','trialing']).select_related('plan').order_by('-created_at').first()
            if subscription and subscription.plan:
                limit=subscription.plan.max_applications_per_month
                month=timezone.now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
                used=FinancialApplication.objects.filter(organization=org,created_at__gte=month).count()
                if limit and used>=limit: raise serializers.ValidationError({'subscription':'The monthly application limit for this plan has been reached.'})
        return attrs
    def create(self, validated_data):
        req = self.context['request']
        validated_data.update(organization=get_user_organization(req.user, req), created_by=req.user)
        role=get_user_role_context(req.user,req)
        if role['hierarchy_level']<50 and getattr(req.user,'employee',None):
            validated_data.setdefault('assigned_employee',req.user.employee)
        if not validated_data.get('application_code'):
            import uuid
            validated_data['application_code'] = f'APP-{uuid.uuid4().hex[:8].upper()}'
        return super().create(validated_data)

class ApplicationStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationStatusHistory
        fields = '__all__'

class ApplicationChecklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationChecklist
        fields = '__all__'
        read_only_fields = ('updated_by', 'updated_at')
    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        app=attrs.get('application',getattr(instance,'application',None)); doc=attrs.get('document',getattr(instance,'document',None))
        if not org or not app or app.organization_id!=org.id: raise serializers.ValidationError({'application':'Application must belong to your organization.'})
        if doc and (doc.organization_id!=org.id or doc.application_id!=app.id): raise serializers.ValidationError({'document':'Choose a document uploaded to this application.'})
        if attrs.get('status')==ApplicationChecklist.Status.ACCEPTED and not doc: raise serializers.ValidationError({'document':'An accepted checklist item must reference a document.'})
        return attrs
