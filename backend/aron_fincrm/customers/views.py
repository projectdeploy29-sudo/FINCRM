from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from customers.models import Customer, CustomerTag
from customers.serializers import CustomerSerializer
from communications.models import Interaction
from applications.models import FinancialApplication
from tasks.models import CostomerFollowUp
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin


class CustomerViewSet(viewsets.ModelViewSet):
    """
    CRUD for Customers with search, tags, and full activity timeline.
    """
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'customer_type', 'segment', 'preferred_channel']
    search_fields = ['full_name', 'legal_name', 'primary_phone', 'email', 'customer_code', 'city']
    ordering_fields = ['created_at', 'full_name']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]

    def get_queryset(self):
        org = get_user_organization(self.request.user, self.request)
        if not org:
            return Customer.objects.none()

        qs = Customer.objects.filter(organization=org).select_related(
            'created_by__user', 'assigned_to__user'
        ).prefetch_related('tags')
        department=self.request.query_params.get('department'); team=self.request.query_params.get('team')
        if department: qs=qs.filter(Q(created_by__department_id=department)|Q(assigned_to__department_id=department))
        if team: qs=qs.filter(Q(created_by__team_id=team)|Q(assigned_to__team_id=team))
        role=get_user_role_context(self.request.user,self.request); level=role['hierarchy_level']; user=self.request.user
        if level<90:
            employee=getattr(user,'employee',None)
            if level>=70:
                manager=user.manager_set.first() if hasattr(user,'manager_set') else None
                departments=manager.managed_departments.all() if manager else []
                qs=qs.filter(Q(created_by__department__in=departments)|Q(assigned_to__department__in=departments)).distinct()
            elif level>=50:
                profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
                teams=profile.teams.all() if profile else []
                qs=qs.filter(Q(created_by__team__in=teams)|Q(assigned_to__team__in=teams)).distinct()
            elif employee: qs=qs.filter(assigned_to=employee)
            else: qs=qs.none()

        # Filter by tag if requested
        tag = self.request.query_params.get('tag')
        if tag:
            qs = qs.filter(tags__tag__iexact=tag)

        # Include archived or not
        include_archived = self.request.query_params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            qs = qs.filter(archived_at__isnull=True)

        return qs

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        """
        GET /api/v1/customers/<id>/timeline/
        Assembles a comprehensive chronological feed of all customer activities:
        - Interactions (calls, meetings, notes, WhatsApp)
        - Financial applications (loans & insurances)
        - Follow-up logs
        """
        customer = self.get_object()
        events = []

        # 1. Interactions
        interactions = Interaction.objects.filter(customer=customer).select_related('created_by', 'employee__user')
        for item in interactions:
            events.append({
                'type': 'interaction',
                'id': str(item.id),
                'interaction_type': item.interaction_type,
                'direction': item.direction,
                'subject': item.subject,
                'content': item.content,
                'duration': item.duration,
                'outcome': item.outcome,
                'occurred_at': item.occurred_at,
                'performed_by': item.created_by.get_full_name() or item.created_by.username,
            })

        # 2. Financial Applications
        applications = FinancialApplication.objects.filter(customer=customer).select_related('assigned_employee__user')
        for app in applications:
            events.append({
                'type': 'application',
                'id': str(app.id),
                'application_code': app.application_code,
                'status': app.status,
                'requested_amount': str(app.requested_amount) if app.requested_amount else None,
                'approved_amount': str(app.approved_amount) if app.approved_amount else None,
                'occurred_at': app.created_at,
                'performed_by': (app.assigned_employee.user.get_full_name() or app.assigned_employee.user.username) if app.assigned_employee else None,
            })

        # 3. Follow-ups
        followups = CostomerFollowUp.objects.filter(customer=customer).select_related('created_by__user')
        for f in followups:
            events.append({
                'type': 'followup',
                'id': str(f.id),
                'followup_type': f.followup_type,
                'status': f.status,
                'outcome': f.outcome,
                'occurred_at': f.scheduled_at,
                'performed_by': (f.created_by.user.get_full_name() or f.created_by.user.username) if f.created_by else None,
            })

        # Sort all events chronologically descending (newest first)
        events.sort(key=lambda x: x['occurred_at'], reverse=True)

        return Response(
            {
                'customer_id': str(customer.id),
                'customer_name': customer.full_name,
                'total_events': len(events),
                'timeline': events,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def tag(self, request, pk=None):
        """
        POST /api/v1/customers/<id>/tag/
        Adds or toggles a tag on the customer (e.g. {"tag": "VIP"}).
        """
        customer = self.get_object()
        tag_value = request.data.get('tag')
        if tag_value not in dict(CustomerTag.Tag.choices):
            return Response({"detail": "Choose a valid tag."}, status=status.HTTP_400_BAD_REQUEST)

        tag_obj, created = CustomerTag.objects.get_or_create(customer=customer, tag=tag_value)
        if not created:
            # Toggle off
            tag_obj.delete()
            action_done = "removed"
        else:
            action_done = "added"

        return Response(
            {
                "detail": f"Tag '{tag_value}' {action_done}.",
                "tags": list(customer.tags.values_list('tag', flat=True)),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """
        POST /api/v1/customers/<id>/archive/
        Soft-archives customer.
        """
        customer = self.get_object()
        customer.archived_at = timezone.now()
        customer.status = Customer.Status.INACTIVE
        customer.save(update_fields=['archived_at', 'status', 'updated_at'])
        return Response({"detail": "Customer archived successfully."}, status=status.HTTP_200_OK)
