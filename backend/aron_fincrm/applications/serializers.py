from decimal import Decimal
from rest_framework import serializers
from applications.models import FinancialApplication, ApplicationStatusHistory
from employes.models import Employee
from organizations.tenant import get_user_organization, get_user_role_context
from organizations.dates import OrganizationDateTimeField

class FinancialApplicationSerializer(serializers.ModelSerializer):
    application_code = serializers.CharField(required=False, allow_blank=True)
    requested_amount = serializers.DecimalField(max_digits=15, decimal_places=2, required=True, min_value=Decimal('0.01'))
    assigned_employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all(), required=True)
    follow_up_at = OrganizationDateTimeField(required=True)
    customer_name = serializers.SerializerMethodField(read_only=True)
    lead_name = serializers.SerializerMethodField(read_only=True)
    assigned_employee_name = serializers.SerializerMethodField(read_only=True)
    label = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = FinancialApplication
        fields = '__all__'
        read_only_fields = ('organization', 'created_by', 'status', 'lead', 'approved_amount', 'disbursed_amount', 'net_disbursed_amount', 'upfront_deductions_amount', 'interest_calculation_method', 'submitted_at', 'disbursed_at', 'completed_at', 'created_at', 'updated_at', 'monthly_repayment_amount', 'next_payment_due_date')
    application_type = serializers.CharField(required=True, allow_blank=False)
    def validate_customer(self, customer):
        req=self.context['request']; org=get_user_organization(req.user, req)
        if not org or customer.organization_id != org.id:
            raise serializers.ValidationError('Customer must belong to your organization.')
        role=get_user_role_context(req.user,req)
        if role['hierarchy_level']<50:
            employee=getattr(req.user,'employee',None)
            if not employee or customer.assigned_to_id!=employee.id:
                raise serializers.ValidationError('Customer must be assigned to you.')
        return customer

    def get_customer_name(self, obj):
        return obj.customer.full_name if obj.customer_id else None

    def get_lead_name(self, obj):
        return obj.lead.contact_name if obj.lead_id else None

    def get_assigned_employee_name(self, obj):
        if obj.assigned_employee_id and obj.assigned_employee.user:
            user = obj.assigned_employee.user
            return user.get_full_name() or user.username
        return None

    def get_label(self, obj):
        customer_name = obj.customer.full_name or obj.customer.legal_name or obj.application_code
        principal = obj.disbursed_amount
        net_paid = obj.net_disbursed_amount if obj.net_disbursed_amount is not None else principal
        if principal is not None:
            method_label = dict(FinancialApplication.InterestCalculationMethod.choices).get(
                obj.interest_calculation_method, obj.interest_calculation_method,
            )
            rate_label = f'{obj.annual_interest_rate}% at {method_label}' if obj.annual_interest_rate is not None else method_label
            tenure_label = f' · {obj.loan_tenure_months} installments' if obj.loan_tenure_months else ''
            return (
                f'{obj.application_code} · {customer_name} · principal {obj.currency} {principal:,.2f}'
                f' · net paid {obj.currency} {net_paid:,.2f} · {rate_label}{tenure_label}'
            )
        return f'{obj.application_code} · {customer_name} · amount not recorded'
    def validate(self,attrs):
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        lead=attrs.get('lead',getattr(instance,'lead',None)); employee=attrs.get('assigned_employee',getattr(instance,'assigned_employee',None))
        if lead and (not org or lead.organization_id!=org.id): raise serializers.ValidationError({'lead':'Lead must belong to your organization.'})
        if employee and (not org or employee.organization_id!=org.id): raise serializers.ValidationError({'assigned_employee':'Employee must belong to your organization.'})
        if employee and (not instance or employee != instance.assigned_employee) and employee.employment_status != employee.EmploymentStatus.ACTIVE:
            raise serializers.ValidationError({'assigned_employee':'Assign applications only to active employees.'})
        role=get_user_role_context(req.user,req); level=role['hierarchy_level']; user=req.user
        if lead and level<50:
            employee=getattr(user,'employee',None)
            if not employee or lead.assigned_to_id!=employee.id:
                raise serializers.ValidationError({'lead':'Lead must be assigned to you.'})
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
        if customer and lead and lead.customer_id and lead.customer_id!=customer.id:
            raise serializers.ValidationError({'lead':'The application customer must match the lead customer.'})
        if lead and lead.application_id and (not instance or lead.application_id!=instance.id):
            raise serializers.ValidationError({'lead':'This lead is already linked to another application.'})
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
