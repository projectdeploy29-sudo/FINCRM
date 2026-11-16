from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from organizations.tenant import get_user_organization, get_user_role_context

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer enriching token response and claims with
    organization, role hierarchy, and module permissions.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        role_ctx = get_user_role_context(user)
        token['username'] = user.username
        token['email'] = user.email
        token['role'] = role_ctx['role_code']
        token['hierarchy_level'] = role_ctx['hierarchy_level']
        if role_ctx['organization']:
            token['org_id'] = str(role_ctx['organization'].id)
            token['org_name'] = role_ctx['organization'].name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        role_ctx = get_user_role_context(self.user, self.context.get('request'))
        org = role_ctx['organization']

        data['user'] = {
            'id': str(self.user.id),
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
        }
        data['organization'] = {
            'id': str(org.id),
            'name': org.name,
            'slug': getattr(org, 'slug', ''),
            'currency': getattr(org, 'currency', 'INR'),
            'timezone': getattr(org, 'timezone', 'Asia/Kolkata'),
        } if org else None

        data['role'] = {
            'code': role_ctx['role_code'],
            'name': role_ctx['role_name'],
            'hierarchy_level': role_ctx['hierarchy_level'],
        }
        data['department'] = {
            'id': str(role_ctx['department'].id),
            'name': role_ctx['department'].name,
        } if role_ctx.get('department') else None

        data['team'] = {
            'id': str(role_ctx['team'].id),
            'name': role_ctx['team'].name,
        } if role_ctx.get('team') else None

        data['permissions'] = role_ctx['permissions']
        data['available_roles'] = role_ctx.get('available_roles', [])
        return data


class UserMeSerializer(serializers.ModelSerializer):
    """
    Serializer providing comprehensive profile and RBAC context for the authenticated user.
    """
    organization = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    available_roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
            'organization',
            'role',
            'department',
            'team',
            'permissions',
            'available_roles',
        ]

    def get_organization(self, obj):
        org = get_user_organization(obj)
        if not org:
            return None
        return {
            'id': str(org.id),
            'name': org.name,
            'slug': getattr(org, 'slug', ''),
            'currency': getattr(org, 'currency', 'INR'),
            'timezone': getattr(org, 'timezone', 'Asia/Kolkata'),
            'is_active': org.is_active,
        }

    def get_role(self, obj):
        ctx = get_user_role_context(obj, self.context.get('request'))
        return {
            'code': ctx['role_code'],
            'name': ctx['role_name'],
            'hierarchy_level': ctx['hierarchy_level'],
            'profile_id': ctx['profile_id'],
        }

    def get_department(self, obj):
        ctx = get_user_role_context(obj, self.context.get('request'))
        dept = ctx.get('department')
        if not dept:
            return None
        return {'id': str(dept.id), 'name': dept.name}

    def get_team(self, obj):
        ctx = get_user_role_context(obj, self.context.get('request'))
        team = ctx.get('team')
        if not team:
            return None
        return {'id': str(team.id), 'name': team.name}

    def get_permissions(self, obj):
        ctx = get_user_role_context(obj, self.context.get('request'))
        return ctx.get('permissions', [])

    def get_available_roles(self, obj):
        ctx = get_user_role_context(obj, self.context.get('request'))
        return ctx.get('available_roles', [])


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)
