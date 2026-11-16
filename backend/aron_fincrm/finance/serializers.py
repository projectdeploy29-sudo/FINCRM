from decimal import Decimal, InvalidOperation
from rest_framework import serializers
from django.db import transaction
from django.db.models import Sum
from finance.models import RepaymentSchedule, RepaymentPayment
from organizations.tenant import get_user_organization

class RepaymentScheduleSerializer(serializers.ModelSerializer):
    outstanding_amount=serializers.ReadOnlyField(); is_overdue=serializers.ReadOnlyField()
    class Meta: model=RepaymentSchedule; fields='__all__'; read_only_fields=('organization',)

class RepaymentPaymentSerializer(serializers.ModelSerializer):
    payment_proof_available=serializers.SerializerMethodField()
    class Meta: model=RepaymentPayment; fields='__all__'; read_only_fields=('organization','recorded_by','verified_by','verification_status','created_at'); extra_kwargs={'payment_proof':{'write_only':True}}
    def get_payment_proof_available(self,obj): return bool(obj.payment_proof)
    def validate_repayment_schedule(self, schedule):
        org=get_user_organization(self.context['request'].user,self.context['request'])
        if not org or schedule.organization_id != org.id: raise serializers.ValidationError('Schedule must belong to your organization.')
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
