from rest_framework import serializers
from django.db import transaction
from permitions.models import Role, Permission, RolePermission
from organizations.tenant import get_user_organization


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'module', 'action', 'codename', 'description']


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    permission_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Role
        fields = [
            'id',
            'name',
            'code',
            'description',
            'is_system_role',
            'permissions',
            'permission_ids',
            'created_at',
        ]
        read_only_fields = ['id', 'is_system_role', 'created_at']

    def get_permissions(self, obj):
        return list(
            RolePermission.objects.filter(role=obj).values(
                'permission__id',
                'permission__codename',
                'permission__module',
                'permission__action',
                'permission__description',
            )
        )

    def create(self, validated_data):
        permission_ids = validated_data.pop('permission_ids', [])
        user = self.context['request'].user
        org = get_user_organization(user)
        validated_data['organization'] = org
        validated_data['is_system_role'] = False

        with transaction.atomic():
            role = Role.objects.create(**validated_data)
            if permission_ids:
                perms = Permission.objects.filter(id__in=permission_ids)
                RolePermission.objects.bulk_create([
                    RolePermission(role=role, permission=p) for p in perms
                ])
            return role

    def update(self, instance, validated_data):
        if instance.is_system_role:
            raise serializers.ValidationError("System default roles cannot be modified.")

        permission_ids = validated_data.pop('permission_ids', None)
        with transaction.atomic():
            for attr, val in validated_data.items():
                setattr(instance, attr, val)
            instance.save()

            if permission_ids is not None:
                RolePermission.objects.filter(role=instance).delete()
                perms = Permission.objects.filter(id__in=permission_ids)
                RolePermission.objects.bulk_create([
                    RolePermission(role=instance, permission=p) for p in perms
                ])
            return instance
