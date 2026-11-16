from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from organizations.models import organizations_organization
from permitions.models import Role

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
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrganizationRegistrationSerializer(serializers.Serializer):
    # Organization fields
    organization_name = serializers.CharField(max_length=200)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    slug = serializers.SlugField(max_length=200, required=False, allow_blank=True)
    org_email = serializers.EmailField(required=False, allow_blank=True)
    org_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    currency = serializers.CharField(max_length=3, default='INR')

    # Admin User fields
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
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
        with transaction.atomic():
            # 1. Create Organization
            org = organizations_organization.objects.create(
                name=validated_data['organization_name'],
                legal_name=validated_data.get('legal_name', ''),
                slug=validated_data['slug'],
                email=validated_data.get('org_email', ''),
                phone=validated_data.get('org_phone', ''),
                city=validated_data.get('city', ''),
                state=validated_data.get('state', ''),
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
                is_staff=True,
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
        if department and department.organization_id!=org.id: raise serializers.ValidationError({'department':'Department must belong to your organization.'})
        if lead and lead.organization_id!=org.id: raise serializers.ValidationError({'team_lead':'Team lead must belong to your organization.'})
        if leader and leader.organization_id!=org.id: raise serializers.ValidationError({'team_leader':'Team leader must belong to your organization.'})
        if lead and department and lead.department_id and lead.department_id!=department.id: raise serializers.ValidationError({'team_lead':'Team lead must belong to the selected department.'})
        return attrs

    def create(self, validated_data):
        from organizations.tenant import get_user_organization
        user = self.context['request'].user
        validated_data['organization'] = get_user_organization(user)
        return super().create(validated_data)

