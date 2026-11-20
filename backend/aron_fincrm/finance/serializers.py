from decimal import Decimal, InvalidOperation
from rest_framework import serializers
from django.db import transaction
from django.db.models import Sum
from finance.models import RepaymentSchedule, RepaymentPayment
from organizations.tenant import get_user_organization, get_user_role_context
from organizations.dates import organization_local_date

class RepaymentScheduleSerializer(serializers.ModelSerializer):
    outstanding_amount=serializers.ReadOnlyField()
    is_overdue=serializers.SerializerMethodField()
    label=serializers.SerializerMethodField()
    class Meta: model=RepaymentSchedule; fields='__all__'; read_only_fields=('organization',)
    def get_label(self, obj):
        customer_name = obj.customer.full_name or obj.customer.legal_name
        reference = obj.lead.lead_code if obj.lead_id else obj.application.application_code
        return f'{reference} · {customer_name} · installment {obj.installment_number} · due {obj.due_date} · outstanding {obj.application.currency} {obj.outstanding_amount:,.2f}'
    def get_is_overdue(self, obj):
        return (
            obj.due_date < organization_local_date(self.context.get('request'))
            and obj.outstanding_amount > 0
            and obj.status not in (RepaymentSchedule.Status.WAIVED, RepaymentSchedule.Status.CANCELLED)
        )

class RepaymentPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepaymentPayment
        exclude = ('payment_proof',)
        read_only_fields = ('organization', 'recorded_by', 'verified_by', 'verification_status', 'created_at')
    def validate_repayment_schedule(self, schedule):
        request=self.context['request']; user=request.user
        org=get_user_organization(user,request)
        if not org or schedule.organization_id != org.id: raise serializers.ValidationError('Schedule must belong to your organization.')
        role=get_user_role_context(user,request); level=role['hierarchy_level']; employee=getattr(user,'employee',None); app=schedule.application
        if level<50 and (not employee or app.assigned_employee_id!=employee.id): raise serializers.ValidationError('This loan must be assigned to you.')
        if 50<=level<70:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            if not profile or not app.assigned_employee_id or not profile.teams.filter(pk=app.assigned_employee.team_id).exists(): raise serializers.ValidationError('This loan must belong to a team you lead.')
        if 70<=level<90:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            if not manager or not app.assigned_employee_id or not manager.managed_departments.filter(pk=app.assigned_employee.department_id).exists(): raise serializers.ValidationError('This loan must belong to a department you manage.')
        try: amount=Decimal(str(self.initial_data.get('amount','0')))
        except (InvalidOperation,TypeError): raise serializers.ValidationError('Enter a valid payment amount.')
        if amount<=0: raise serializers.ValidationError('Payment amount must be greater than zero.')
        pending=schedule.payments.filter(verification_status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if amount > max(schedule.outstanding_amount-pending,Decimal('0')): raise serializers.ValidationError('Payment exceeds the remaining amount, including pending receipts.')
        return schedule
    def validate_payment_date(self,value):
        if value > organization_local_date(self.context['request']):
            raise serializers.ValidationError('A payment date cannot be in the future. Historical payments are allowed.')
        return value
    def create(self, validated_data):
        req=self.context['request']; employee=getattr(req.user,'employee',None)
        if not employee: raise serializers.ValidationError('An employee profile is required to record payments.')
        if employee.employment_status != employee.EmploymentStatus.ACTIVE: raise serializers.ValidationError('An active employee profile is required to record payments.')
        org=get_user_organization(req.user,req); schedule=validated_data['repayment_schedule']
        with transaction.atomic():
            schedule=RepaymentSchedule.objects.select_for_update().get(pk=schedule.pk,organization=org)
            pending=schedule.payments.filter(verification_status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            if validated_data['amount']>max(schedule.outstanding_amount-pending,Decimal('0')):raise serializers.ValidationError({'amount':'Payment is above the remaining schedule amount.'})
            return super().create({**validated_data,'organization':org,'repayment_schedule':schedule,'recorded_by':employee})
