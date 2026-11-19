from decimal import Decimal, InvalidOperation
from rest_framework import serializers
from django.db import transaction
from django.db.models import Sum
from finance.models import RepaymentSchedule, RepaymentPayment
from organizations.tenant import get_user_organization, get_user_role_context

class RepaymentScheduleSerializer(serializers.ModelSerializer):
    outstanding_amount=serializers.ReadOnlyField(); is_overdue=serializers.ReadOnlyField()
    class Meta: model=RepaymentSchedule; fields='__all__'; read_only_fields=('organization',)

class RepaymentPaymentSerializer(serializers.ModelSerializer):
    payment_proof_available=serializers.SerializerMethodField()
    class Meta: model=RepaymentPayment; fields='__all__'; read_only_fields=('organization','recorded_by','verified_by','verification_status','created_at'); extra_kwargs={'payment_proof':{'write_only':True}}
    def get_payment_proof_available(self,obj): return bool(obj.payment_proof)
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
    def validate_payment_proof(self,value):
        if value and value.size>15*1024*1024:raise serializers.ValidationError('Maximum payment proof size is 15 MB.')
        if value and value.content_type not in {'application/pdf','image/jpeg','image/png'}:raise serializers.ValidationError('Only PDF, JPEG and PNG proofs are accepted.')
        return value
    def create(self, validated_data):
        req=self.context['request']; employee=getattr(req.user,'employee',None)
        if not employee: raise serializers.ValidationError('An employee profile is required to record payments.')
        org=get_user_organization(req.user,req); schedule=validated_data['repayment_schedule']
        with transaction.atomic():
            schedule=RepaymentSchedule.objects.select_for_update().get(pk=schedule.pk,organization=org)
            pending=schedule.payments.filter(verification_status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            if validated_data['amount']>max(schedule.outstanding_amount-pending,Decimal('0')):raise serializers.ValidationError({'amount':'Payment is above the remaining schedule amount.'})
            return super().create({**validated_data,'organization':org,'repayment_schedule':schedule,'recorded_by':employee})
