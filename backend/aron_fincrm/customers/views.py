import uuid
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from customers.models import Customer, CustomerTag, CustomerAssignmentHistory, CustomerStatusHistory
from customers.serializers import CustomerSerializer, CustomerAssignmentHistorySerializer
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
        - Customer and lead follow-ups
        - Follow-up logs
        """
        customer = self.get_object()
        events = []

        # Follow-ups
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
    def transition(self, request, pk=None):
        customer = self.get_object()
        new = request.data.get('status')
        allowed = {Customer.Status.NEW: {Customer.Status.CONTACTED}, Customer.Status.CONTACTED: {Customer.Status.UNDER_REVIEW}}
        note = str(request.data.get('notes', '') or '').strip()
        tag = request.data.get('tag')
        if new == Customer.Status.CONTACTED:
            if not note:
                return Response({'notes': 'Add a note describing the customer contact.'}, status=400)
            if tag not in dict(CustomerTag.Tag.choices):
                return Response({'tag': 'Choose the customer tag for this contact.'}, status=400)
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer.pk, organization=customer.organization)
            old = customer.status
            if new not in allowed.get(old, set()):
                return Response({'detail': f'Cannot move customer from {old} to {new}.'}, status=400)
            if new == Customer.Status.CONTACTED:
                existing_tags = set(customer.tags.values_list('tag', flat=True))
                if existing_tags == {tag}:
                    return Response({'tag': 'Choose a different tag to record the required tag change.'}, status=400)
            customer.status = new
            if note:
                customer.notes = '\n'.join(filter(None, [customer.notes, note]))
            customer.save(update_fields=['status', 'notes', 'updated_at'])
            if tag:
                customer.tags.all().delete()
                CustomerTag.objects.create(customer=customer, tag=tag)
            CustomerStatusHistory.objects.create(customer=customer, old_status=old, new_status=new, changed_by=request.user, notes=note)
        return Response(CustomerSerializer(customer, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='convert-to-lead')
    def convert_to_lead(self, request, pk=None):
        from leads.models import Lead, LeadStatusHistory, LeadAssignmentHistory
        from leads.serializers import LeadSerializer
        customer = self.get_object()
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer.pk, organization=customer.organization)
            if customer.status != Customer.Status.UNDER_REVIEW:
                return Response({'detail': 'Only customers under review can be converted to leads.'}, status=400)
            if Lead.objects.filter(customer=customer).exists():
                return Response({'detail': 'This customer already has a lead.'}, status=409)
            from subscriptions.entitlements import enforce_resource_limit
            enforce_resource_limit(customer.organization, 'leads', lock=True)
            assigned = customer.assigned_to
            if not assigned or assigned.employment_status != assigned.EmploymentStatus.ACTIVE:
                return Response({'detail': 'Assign this customer to an active employee before conversion.'}, status=400)
            lead_source = customer.source.lower().replace(' ', '_') if customer.source else Lead.Source.OTHER
            if lead_source not in dict(Lead.Source.choices):
                lead_source = Lead.Source.OTHER
            lead = Lead.objects.create(
                organization=customer.organization, lead_code=f'LEAD-{uuid.uuid4().hex[:8].upper()}',
                contact_name=customer.full_name or customer.legal_name, phone=customer.primary_phone,
                email=customer.email, city=customer.city, state=customer.state,
                assigned_to=assigned, created_by=assigned, customer=customer,
                source=lead_source,
                expected_amount=customer.requested_amount, requested_amount=customer.requested_amount,
                currency=customer.currency, status=Lead.Status.NEW,
            )
            customer.status = Customer.Status.CONVERTED
            customer.save(update_fields=['status', 'updated_at'])
            LeadStatusHistory.objects.create(lead=lead, old_status='', new_status=lead.status, changed_by=request.user, notes='Converted from customer')
            LeadAssignmentHistory.objects.create(lead=lead, new_owner=assigned, assigned_by=request.user, reason='Assigned from customer conversion')
            CustomerStatusHistory.objects.create(customer=customer, old_status=Customer.Status.UNDER_REVIEW, new_status=Customer.Status.CONVERTED, changed_by=request.user, notes='Converted to lead')
        return Response({'detail': 'Customer converted to lead.', 'lead': LeadSerializer(lead, context={'request': request}).data}, status=201)

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

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        customer = self.get_object()
        history = CustomerAssignmentHistory.objects.filter(customer=customer).select_related(
            'previous_owner__user', 'new_owner__user', 'changed_by'
        )
        return Response(CustomerAssignmentHistorySerializer(history, many=True).data)

    @action(detail=True, methods=['get'], url_path='status-history')
    def status_history(self, request, pk=None):
        customer = self.get_object()
        rows = CustomerStatusHistory.objects.filter(customer=customer).select_related('changed_by')
        return Response([{'id': str(x.id), 'old_status': x.old_status, 'new_status': x.new_status, 'changed_by_name': x.changed_by.get_full_name() or x.changed_by.username, 'notes': x.notes, 'changed_at': x.changed_at} for x in rows])
