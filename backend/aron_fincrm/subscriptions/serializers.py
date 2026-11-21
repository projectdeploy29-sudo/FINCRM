import uuid
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from django.db import transaction
from subscriptions.models import Plan, Subscription, Payment
from organizations.tenant import get_user_organization
from employes.models import Employee
from accounts.models import Manager, TeamLead
from applications.models import FinancialApplication


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'id',
            'name',
            'code',
            'description',
            'monthly_price',
            'yearly_price',
            'max_employees',
            'max_leads',
            'features',
            'is_active',
            'created_at',
        ]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id',
            'subscription',
            'amount',
            'currency',
            'provider',
            'provider_payment_id',
            'invoice_reference',
            'status',
            'paid_at',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_details = PlanSerializer(source='plan', read_only=True)
    usage = serializers.SerializerMethodField(read_only=True)
    days_remaining = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'plan',
            'plan_details',
            'Subscriptioncode',
            'billing_cycle',
            'status',
            'start_date',
            'end_date',
            'next_billing_date',
            'cancelled_at',
            'usage',
            'days_remaining',
            'created_at',
        ]
        read_only_fields = ['id', 'Subscriptioncode', 'created_at']

    def get_usage(self, obj):
        org = obj.organization
        now = timezone.now()
        employees_count = (
            Employee.objects.filter(organization=org).count() +
            Manager.objects.filter(organization=org).count() +
            TeamLead.objects.filter(organization=org).count()
        )
        from leads.models import Lead
        leads_count = Lead.objects.filter(organization=org).count()

        return {
            'staff_count': employees_count,
            'max_staff_allowed': obj.plan.max_employees,
            'leads_count': leads_count,
            'max_leads_allowed': obj.plan.max_leads,
        }

    def get_days_remaining(self, obj):
        if obj.end_date:
            delta = obj.end_date - timezone.now()
            return max(delta.days, 0)
        return 0


class SubscribeSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    billing_cycle = serializers.ChoiceField(choices=Subscription.BillingCycle.choices)
    payment_provider = serializers.CharField(max_length=100, default='MANUAL')
    provider_payment_id = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_plan_id(self, value):
        plan = Plan.objects.filter(id=value, is_active=True).first()
        if not plan:
            raise serializers.ValidationError("Active plan with this ID was not found.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        org = get_user_organization(request.user)
        plan = Plan.objects.get(id=validated_data['plan_id'])
        cycle = validated_data['billing_cycle']

        now = timezone.now()
        if cycle == Subscription.BillingCycle.MONTHLY:
            end_date = now + timedelta(days=30)
            amount = plan.monthly_price
        else:
            end_date = now + timedelta(days=365)
            amount = plan.yearly_price

        if amount is None:
            raise serializers.ValidationError({'billing_cycle': 'This plan requires a negotiated contract or pricing setup before it can be activated.'})

        code = f"SUB-{uuid.uuid4().hex[:8].upper()}"

        with transaction.atomic():
            Subscription.objects.filter(organization=org,status__in=['active','trialing']).update(status='cancelled',cancelled_at=now)
            sub = Subscription.objects.create(
                organization=org, plan=plan, Subscriptioncode=code, billing_cycle=cycle,
                status='active', start_date=now, end_date=end_date, next_billing_date=end_date.date(),
            )
            payment=Payment.objects.create(
                subscription=sub, amount=amount, currency=getattr(org, 'currency', 'INR'),
                provider=validated_data.get('payment_provider', 'MANUAL'),
                provider_payment_id=validated_data.get('provider_payment_id', ''),
                invoice_reference=f"INV-{sub.Subscriptioncode}", status='succeeded', paid_at=now,
            )
            sub.payment=payment; sub.save(update_fields=['payment'])
        return sub
