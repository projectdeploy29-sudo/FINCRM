import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from organizations.models import organizations_organization
from permitions.models import Role
from subscriptions.models import PlanCheckout, Subscription, Payment
from subscriptions.registration import hash_registration_token, send_registration_completed

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = organizations_organization
        fields = [
            'id',
            'name',
            'legal_name',
            'slug',
            'email',
            'phone',
            'website',
            'address_line1',
            'address_line2',
            'city',
            'state',
            'pin_code',
            'country',
            'timezone',
            'currency',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise serializers.ValidationError('Choose a valid IANA timezone, such as Asia/Kolkata.')
        return value


class OrganizationRegistrationSerializer(serializers.Serializer):
    registration_token = serializers.CharField(max_length=128, write_only=True)
    # Organization fields
    organization_name = serializers.CharField(max_length=200)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    slug = serializers.SlugField(max_length=200, required=False, allow_blank=True)
    org_email = serializers.EmailField(required=False, allow_blank=True)
    org_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=50, default='Asia/Kolkata')
    currency = serializers.CharField(max_length=3, default='INR')

    # Admin User fields
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise serializers.ValidationError('Choose a valid IANA timezone, such as Asia/Kolkata.')
        return value

    def validate_password(self, value):
        candidate = User(
            username=self.initial_data.get('username', ''),
            email=self.initial_data.get('email', ''),
            first_name=self.initial_data.get('first_name', ''),
            last_name=self.initial_data.get('last_name', ''),
        )
        try:
            validate_password(value, candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        token_hash = hash_registration_token(attrs['registration_token'])
        checkout = PlanCheckout.objects.filter(
            registration_token_hash=token_hash,
            status=PlanCheckout.Status.PAID,
            registration_token_used_at__isnull=True,
            registration_token_expires_at__gt=timezone.now(),
        ).select_related('plan').first()
        if not checkout:
            raise serializers.ValidationError({'registration_token': 'This registration link is invalid, expired, or already used.'})
        if checkout.enterprise_inquiry_id and not attrs.get('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Confirm your password to complete Enterprise registration.'})
        if attrs.get('confirm_password') and attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        if checkout.purchaser_email.casefold() != attrs['email'].strip().casefold():
            raise serializers.ValidationError({'email': 'Use the email address that received the registration link.'})
        if checkout.enterprise_inquiry_id:
            expected_name = checkout.organization.name if checkout.organization_id else checkout.enterprise_inquiry.organization_name
            if attrs['organization_name'].strip().casefold() != expected_name.strip().casefold():
                raise serializers.ValidationError({'organization_name': 'Use the organization name from the Enterprise invitation.'})
        attrs['checkout_id'] = checkout.id

        org_name = attrs.get('organization_name')
        slug = attrs.get('slug')
        if not slug:
            base_slug = slugify(org_name)
            slug = base_slug
            counter = 1
            while organizations_organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            attrs['slug'] = slug
        elif organizations_organization.objects.filter(slug=slug).exists():
            raise serializers.ValidationError({"slug": "This organization slug is already in use."})
        return attrs

    def create(self, validated_data):
        registration_token = validated_data.pop('registration_token')
        validated_data.pop('confirm_password', None)
        checkout_id = validated_data.pop('checkout_id')
        with transaction.atomic():
            claimed_at = timezone.now()
            claimed = PlanCheckout.objects.filter(
                id=checkout_id,
                registration_token_hash=hash_registration_token(registration_token),
                status=PlanCheckout.Status.PAID,
                registration_token_used_at__isnull=True,
                registration_token_expires_at__gt=claimed_at,
            ).update(status=PlanCheckout.Status.COMPLETED, registration_token_used_at=claimed_at)
            if claimed != 1:
                raise serializers.ValidationError({'registration_token': 'This registration link is invalid, expired, or already used.'})
            checkout = PlanCheckout.objects.select_related('plan').get(id=checkout_id)
            if checkout.purchaser_email.casefold() != validated_data['email'].strip().casefold():
                raise serializers.ValidationError({'email': 'Use the email address that received the registration link.'})

            # 1. Create Organization
            if checkout.organization_id:
                org = checkout.organization
            else:
                org = organizations_organization.objects.create(
                    name=validated_data['organization_name'],
                    legal_name=validated_data.get('legal_name', ''),
                    slug=validated_data['slug'],
                    email=validated_data.get('org_email', ''),
                    phone=validated_data.get('org_phone', ''),
                    city=validated_data.get('city', ''),
                    state=validated_data.get('state', ''),
                    timezone=validated_data.get('timezone', 'Asia/Kolkata'),
                    currency=validated_data.get('currency', 'INR'),
                )

            # 2. Create Org Admin User
            user = User.objects.create_user(
                username=validated_data['username'],
                email=validated_data['email'],
                password=validated_data['password'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                default_organization=org,
                is_staff=False,
            )

            # 3. Create or assign Org Admin Role for this organization
            org_admin_role, _ = Role.objects.get_or_create(
                organization=org,
                code='org_admin',
                defaults={
                    'name': 'Organization Admin',
                    'description': 'Full administrative control over this organization',
                    'is_system_role': True,
                }
            )

            # Activate the plan only after the registration link is redeemed.
            now = timezone.now()
            cycle_days = 30 if checkout.billing_cycle == Subscription.BillingCycle.MONTHLY else 365
            duration = timedelta(days=cycle_days * (checkout.duration_count or 1))
            subscription = Subscription.objects.create(
                organization=org,
                plan=checkout.plan,
                Subscriptioncode='SUB-' + uuid.uuid4().hex[:12].upper(),
                billing_cycle=checkout.billing_cycle,
                status=Subscription.Status.ACTIVE,
                start_date=now,
                end_date=now + duration,
                next_billing_date=(now + timedelta(days=cycle_days)).date() if checkout.payment_mode == 'recurring' else (now + duration).date(),
                razorpay_subscription_id=checkout.razorpay_subscription_id or '',
            )
            payment = Payment.objects.filter(checkout=checkout, status=Payment.Status.SUCCEEDED).order_by('-paid_at').first()
            if payment is None:
                if checkout.payment_mode != 'recurring':
                    payment = Payment.objects.create(
                        subscription=subscription,
                        checkout=checkout,
                        amount=checkout.amount,
                        currency=checkout.currency,
                        provider='RAZORPAY',
                        provider_payment_id=checkout.razorpay_payment_id or '',
                        invoice_reference='INV-' + subscription.Subscriptioncode,
                        status=Payment.Status.SUCCEEDED,
                        paid_at=checkout.paid_at,
                    )
            else:
                payment.subscription = subscription
                payment.invoice_reference = 'INV-' + subscription.Subscriptioncode
                payment.save(update_fields=['subscription', 'invoice_reference'])
            if payment:
                subscription.payment = payment
                subscription.save(update_fields=['payment'])
            if checkout.enterprise_inquiry_id:
                from subscriptions.models import EnterpriseInquiry
                EnterpriseInquiry.objects.filter(pk=checkout.enterprise_inquiry_id).update(
                    organization=org,
                    status=EnterpriseInquiry.Status.COMPLETED,
                )
                transaction.on_commit(
                    lambda completed_checkout=checkout, completed_org_name=org.name: send_registration_completed(
                        completed_checkout, completed_org_name,
                    )
                )
            # 4. Generate JWT Tokens
            refresh = RefreshToken.for_user(user)
            refresh['org_id'] = str(org.id)
            refresh['role'] = 'org_admin'
            refresh['hierarchy_level'] = 90

            return {
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'organization': OrganizationSerializer(org).data,
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': 'org_admin',
                }
            }


class DepartmentSerializer(serializers.ModelSerializer):
    manager_details = serializers.SerializerMethodField(read_only=True)
    teams_count = serializers.IntegerField(read_only=True, default=0)
    employees_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        from organizations.models import Department
        model = Department
        fields = [
            'id',
            'name',
            'description',
            'manager',
            'manager_details',
            'is_active',
            'teams_count',
            'employees_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_manager_details(self, obj):
        if not obj.manager:
            return None
        m = obj.manager
        user = m.user
        return {
            'id': str(m.id),
            'code': m.code,
            'name': user.get_full_name() or user.username,
            'email': m.work_email or user.email,
            'phone': m.work_phone,
            'designation': m.designation,
        }

    def validate_manager(self,manager):
        from organizations.tenant import get_user_organization
        org=get_user_organization(self.context['request'].user,self.context['request'])
        if manager and (not org or manager.organization_id!=org.id): raise serializers.ValidationError('Manager must belong to your organization.')
        if manager and manager.employment_status!=manager.ManagerStatus.ACTIVE: raise serializers.ValidationError('Choose an active manager.')
        return manager

    def create(self, validated_data):
        from organizations.tenant import get_user_organization
        user = self.context['request'].user
        validated_data['organization'] = get_user_organization(user)
        return super().create(validated_data)


class TeamSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    team_lead_details = serializers.SerializerMethodField(read_only=True)
    members_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        from organizations.models import Team
        model = Team
        fields = [
            'id',
            'department',
            'department_name',
            'name',
            'description',
            'team_lead',
            'team_leader',
            'team_lead_details',
            'is_active',
            'members_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_team_lead_details(self, obj):
        if obj.team_lead:
            tl = obj.team_lead
            user = tl.user
            return {
                'id': str(tl.id),
                'code': tl.code,
                'name': (user.get_full_name() or user.username) if user else tl.code,
                'email': tl.work_email or (user.email if user else ''),
                'phone': tl.work_phone,
                'designation': tl.designation,
            }
        elif obj.team_leader:
            emp = obj.team_leader
            user = emp.user
            return {
                'id': str(emp.id),
                'code': emp.employee_code,
                'name': user.get_full_name() or user.username,
                'email': emp.work_email or user.email,
                'phone': emp.work_phone,
                'designation': emp.designation,
            }
        return None

    def validate(self,attrs):
        from organizations.tenant import get_user_organization
        req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
        department=attrs.get('department',getattr(instance,'department',None)); lead=attrs.get('team_lead',getattr(instance,'team_lead',None)); leader=attrs.get('team_leader',getattr(instance,'team_leader',None))
        if not org: raise serializers.ValidationError('Organization context is required.')
        if not department: raise serializers.ValidationError({'department':'Choose a department for this team.'})
        if department.organization_id!=org.id: raise serializers.ValidationError({'department':'Department must belong to your organization.'})
        if not department.is_active: raise serializers.ValidationError({'department':'Choose an active department.'})
        if lead and lead.organization_id!=org.id: raise serializers.ValidationError({'team_lead':'Team lead must belong to your organization.'})
        if leader and leader.organization_id!=org.id: raise serializers.ValidationError({'team_leader':'Team leader must belong to your organization.'})
        if lead and lead.employment_status!=lead.teamStatus.ACTIVE: raise serializers.ValidationError({'team_lead':'Choose an active team lead.'})
        if leader and leader.employment_status!=leader.EmploymentStatus.ACTIVE: raise serializers.ValidationError({'team_leader':'Choose an active employee team lead.'})
        if department and not department.is_active: raise serializers.ValidationError({'department':'Choose an active department.'})
        if lead and department and lead.department_id!=department.id: raise serializers.ValidationError({'team_lead':'Team lead must belong to the selected department.'})
        if leader and department and leader.department_id!=department.id: raise serializers.ValidationError({'team_leader':'Team leader must belong to the selected department.'})
        return attrs

    def create(self, validated_data):
        from organizations.tenant import get_user_organization
        user = self.context['request'].user
        validated_data['organization'] = get_user_organization(user)
        return super().create(validated_data)

