from rest_framework import serializers

from communications.models import MessageDraft
from organizations.tenant import get_user_organization, get_user_role_context


class MessageDraftSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MessageDraft
        fields = [
            'id', 'customer', 'customer_name', 'channel', 'subject', 'message',
            'status', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'created_by_name', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def validate_customer(self, customer):
        request = self.context['request']
        user = request.user
        org = get_user_organization(user, request)
        if not org or customer.organization_id != org.id:
            raise serializers.ValidationError('Customer must belong to your organization.')
        level = get_user_role_context(user, request)['hierarchy_level']
        employee = getattr(user, 'employee', None)
        if level < 30:
            raise serializers.ValidationError('Only organization staff can create internal message drafts.')
        if level < 50 and (not employee or customer.assigned_to_id != employee.id):
            raise serializers.ValidationError('Customer must be assigned to you.')
        if 50 <= level < 70:
            profile = user.teamlead_profiles.first() if hasattr(user, 'teamlead_profiles') else None
            in_scope = bool(profile and (
                (customer.assigned_to_id and profile.teams.filter(pk=customer.assigned_to.team_id).exists())
                or (customer.created_by_id and customer.created_by.team_id and profile.teams.filter(pk=customer.created_by.team_id).exists())
            ))
            if not in_scope:
                raise serializers.ValidationError('Customer must belong to a team you lead.')
        if 70 <= level < 90:
            manager = user.manager_set.first() if hasattr(user, 'manager_set') else None
            in_scope = bool(manager and (
                (customer.assigned_to_id and manager.managed_departments.filter(pk=customer.assigned_to.department_id).exists())
                or (customer.created_by_id and customer.created_by.department_id and manager.managed_departments.filter(pk=customer.created_by.department_id).exists())
            ))
            if not in_scope:
                raise serializers.ValidationError('Customer must belong to a department you manage.')
        return customer

    def create(self, validated_data):
        request = self.context['request']
        validated_data['organization'] = get_user_organization(request.user, request)
        validated_data['created_by'] = request.user
        validated_data.setdefault('status', MessageDraft.Status.DRAFT)
        return super().create(validated_data)
