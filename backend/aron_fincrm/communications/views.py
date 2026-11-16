from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from communications.models import Interaction, InteractionAttendee, MessageDraft
from communications.serializers import InteractionSerializer, InteractionAttendeeSerializer, MessageDraftSerializer
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsTeamLead


class InteractionViewSet(viewsets.ModelViewSet):
    """
    CRUD for Interactions (calls, emails, meetings, WhatsApp, notes).
    Can be filtered by customer, lead, or application.
    """
    serializer_class = InteractionSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['customer', 'lead', 'application', 'interaction_type', 'direction']
    search_fields = ['subject', 'content', 'outcome']
    ordering_fields = ['occurred_at', 'created_at']
    ordering = ['-occurred_at']

    def get_queryset(self):
        org = get_user_organization(self.request.user, self.request)
        if not org:
            return Interaction.objects.none()
        qs=Interaction.objects.filter(organization=org).select_related(
            'customer', 'lead', 'employee__user', 'created_by'
        )
        ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
        if level>=90:return qs
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(employee__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(employee__team__in=teams)
        emp=getattr(user,'employee',None)
        return qs.filter(employee=emp) if emp else qs.filter(created_by=user)


class MessageDraftViewSet(viewsets.ModelViewSet):
    """
    CRUD for customer communication drafts (SMS, Email, WhatsApp).
    """
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
        qs=MessageDraft.objects.filter(organization=org).select_related(
            'customer', 'created_by'
        )
        return qs if get_user_role_context(self.request.user,self.request)['hierarchy_level']>=50 else qs.filter(created_by=self.request.user)

    def get_permissions(self):
        if self.action=='approve': return [IsAuthenticatedTenant(),IsTeamLead()]
        return [IsAuthenticatedTenant()]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        POST /api/v1/communications/drafts/<id>/approve/
        Marks a message draft as approved and ready for dispatch.
        """
        draft = self.get_object()
        draft.status = MessageDraft.Status.APPROVED
        draft.save(update_fields=['status', 'updated_at'])
        return Response(
            {
                "detail": "Message draft approved successfully.",
                "draft": MessageDraftSerializer(draft).data,
            },
            status=status.HTTP_200_OK,
        )

class InteractionAttendeeViewSet(viewsets.ModelViewSet):
    serializer_class=InteractionAttendeeSerializer; permission_classes=[IsAuthenticatedTenant]
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        return InteractionAttendee.objects.filter(interaction__organization=org).select_related('interaction','employee__user') if org else InteractionAttendee.objects.none()
