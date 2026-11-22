import re
from django.contrib.auth import get_user_model
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from decimal import Decimal
from subscriptions.models import Plan, Subscription, Payment, EnterpriseInquiry
from subscriptions.configuration import is_subscription_checkout_enabled
from employes.models import Employee
from accounts.models import Manager, TeamLead


class PlanSerializer(serializers.ModelSerializer):
    monthly_price = serializers.SerializerMethodField()
    yearly_price = serializers.SerializerMethodField()
    checkout_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            'id',
            'name',
            'code',
            'description',
            'monthly_price',
            'yearly_price',
            'checkout_enabled',
            'max_employees',
            'max_leads',
            'features',
            'is_active',
            'created_at',
        ]

    @staticmethod
    def _checkout_enabled_for_plan(plan):
        return bool(
            is_subscription_checkout_enabled()
            and plan.prices_confirmed
            and plan.monthly_price is not None
            and plan.yearly_price is not None
            and plan.monthly_price > 0
            and plan.yearly_price > 0
        )

    def get_monthly_price(self, obj):
        return obj.monthly_price if self._checkout_enabled_for_plan(obj) else None

    def get_yearly_price(self, obj):
        return obj.yearly_price if self._checkout_enabled_for_plan(obj) else None

    def get_checkout_enabled(self, obj):
        return self._checkout_enabled_for_plan(obj)


class SubscriptionPlanAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'code', 'description', 'currency', 'monthly_price', 'yearly_price',
            'prices_confirmed', 'max_employees', 'max_leads', 'daily_ai_tokens', 'features',
            'storage_limit_mb', 'included_services', 'additional_services', 'terms_conditions',
            'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_code(self, value):
        if value == 'enterprise':
            raise serializers.ValidationError('Enterprise is managed through the inquiry workflow.')
        return value

    def validate_currency(self, value):
        if value.upper() != 'INR':
            raise serializers.ValidationError('Only INR pricing is currently supported.')
        return value.upper()

    def validate(self, attrs):
        monthly = attrs.get('monthly_price', getattr(self.instance, 'monthly_price', None))
        yearly = attrs.get('yearly_price', getattr(self.instance, 'yearly_price', None))
        confirmed = attrs.get('prices_confirmed', getattr(self.instance, 'prices_confirmed', False))
        if confirmed and (monthly is None or yearly is None or monthly <= 0 or yearly <= 0):
            raise serializers.ValidationError({'prices_confirmed': 'Set positive monthly and yearly prices before confirming prices.'})
        return attrs


class PlanCheckoutSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    billing_cycle = serializers.ChoiceField(choices=Subscription.BillingCycle.choices)
    email = serializers.EmailField(required=False)

    def validate_plan_id(self, value):
        if not Plan.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError('Choose an active plan.')
        return value


class PlanCheckoutVerificationSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=256)


class EnterpriseInquirySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    organization_name = serializers.CharField(max_length=200)
    website = serializers.URLField(required=False, allow_blank=True)
    linkedin_url = serializers.URLField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    fax = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=200)

    class Meta:
        model = EnterpriseInquiry
        fields = [
            'full_name',
            'email',
            'phone',
            'organization_name',
            'website',
            'linkedin_url',
            'note',
            'fax',
        ]

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        normalized = value.strip()
        if not re.fullmatch(r'\+?[0-9\s().-]+', normalized):
            raise serializers.ValidationError('Enter a valid phone number using digits and standard separators.')
        digit_count = sum(character.isdigit() for character in normalized)
        if not 7 <= digit_count <= 15:
            raise serializers.ValidationError('Enter a phone number containing 7 to 15 digits.')
        return normalized

    @staticmethod
    def _validate_http_url(value):
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.hostname:
            raise serializers.ValidationError('Use a valid http or https URL.')
        return value

    def validate_website(self, value):
        return self._validate_http_url(value)

    def validate_linkedin_url(self, value):
        return self._validate_http_url(value)

    def create(self, validated_data):
        validated_data.pop('fax', None)
        return super().create(validated_data)


class EnterpriseInquiryAdminSerializer(serializers.ModelSerializer):
    assigned_admin = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_superuser=True, is_active=True),
        required=False,
        allow_null=True,
    )
    assigned_admin_name = serializers.SerializerMethodField()

    class Meta:
        model = EnterpriseInquiry
        fields = [
            'id', 'full_name', 'email', 'phone', 'organization_name', 'website',
            'linkedin_url', 'note', 'status', 'assigned_admin', 'internal_notes',
            'created_at', 'custom_plan', 'payment_link_email_sent_at', 'assigned_admin_name',
        ]
        read_only_fields = ['id', 'created_at', 'custom_plan', 'payment_link_email_sent_at', 'assigned_admin_name']

    def get_assigned_admin_name(self, obj):
        if not obj.assigned_admin:
            return ''
        return obj.assigned_admin.get_full_name() or obj.assigned_admin.username


class EnterprisePlanCreationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    customer_email = serializers.EmailField()
    max_employees = serializers.IntegerField(min_value=1)
    billing_cycle = serializers.ChoiceField(choices=Subscription.BillingCycle.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1.00'))
    currency = serializers.ChoiceField(choices=[('INR', 'INR')], default='INR')
    duration_count = serializers.IntegerField(min_value=1, max_value=120)
    features = serializers.JSONField(default=dict)
    storage_limit_mb = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    included_services = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)
    additional_services = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    terms_conditions = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    recurring = serializers.BooleanField(default=True)

    def validate_customer_email(self, value):
        return value.strip().lower()


class EnterprisePlanAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'code', 'description', 'currency', 'monthly_price',
            'yearly_price', 'max_employees', 'features', 'storage_limit_mb',
            'included_services', 'additional_services', 'terms_conditions',
            'subscription_total_count', 'razorpay_plan_id', 'is_active', 'created_at',
        ]


class EnterprisePlanUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'name', 'description', 'currency', 'monthly_price', 'yearly_price',
            'max_employees', 'features', 'storage_limit_mb', 'included_services',
            'additional_services', 'terms_conditions', 'subscription_total_count',
            'is_active',
        ]

    def validate(self, attrs):
        plan = self.instance
        if plan.razorpay_plan_id:
            for field in ('monthly_price', 'yearly_price', 'subscription_total_count', 'currency'):
                if field in attrs and attrs[field] != getattr(plan, field):
                    raise serializers.ValidationError({field: 'Razorpay recurring billing details are immutable. Create a new custom plan for a price or duration change.'})
        return attrs

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
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    usage = serializers.SerializerMethodField(read_only=True)
    days_remaining = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'organization_name',
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
