from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from communications.models import MessageDraft
from communications.serializers import MessageDraftSerializer
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsTeamLead


class MessageDraftViewSet(viewsets.ModelViewSet):
    """CRUD for customer communication drafts (SMS, Email, WhatsApp)."""
    serializer_class = MessageDraftSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['customer', 'channel', 'status']
    search_fields = ['subject', 'message']
    ordering = ['-created_at']

    def get_queryset(self):
        org = get_user_organization(self.request.user, self.request)
        if not org:
            return MessageDraft.objects.none()
        qs = MessageDraft.objects.filter(organization=org).select_related('customer', 'created_by')
        role = get_user_role_context(self.request.user, self.request)
        level = role['hierarchy_level']
        user = self.request.user
        if level >= 90:
            return qs
        if level >= 70:
            manager = user.manager_set.first() if hasattr(user, 'manager_set') else None
            departments = manager.managed_departments.all() if manager else []
            return qs.filter(
                Q(customer__assigned_to__department__in=departments)
                | Q(customer__created_by__department__in=departments)
                | Q(created_by=user)
            ).distinct()
        if level >= 50:
            profile = user.teamlead_profiles.first() if hasattr(user, 'teamlead_profiles') else None
            teams = profile.teams.all() if profile else []
            return qs.filter(
                Q(customer__assigned_to__team__in=teams)
                | Q(customer__created_by__team__in=teams)
                | Q(created_by=user)
            ).distinct()
        employee = getattr(user, 'employee', None)
        return qs.filter(Q(customer__assigned_to=employee) | Q(created_by=user)).distinct() if employee else qs.none()

    def get_permissions(self):
        if self.action == 'approve':
            return [IsAuthenticatedTenant(), IsTeamLead()]
        return [IsAuthenticatedTenant()]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        draft = self.get_object()
        draft.status = MessageDraft.Status.APPROVED
        draft.save(update_fields=['status', 'updated_at'])
        return Response({
            'detail': 'Message draft approved successfully.',
            'draft': MessageDraftSerializer(draft).data,
        }, status=status.HTTP_200_OK)
