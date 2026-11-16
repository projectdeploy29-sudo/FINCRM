import uuid
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from leads.models import Lead, LeadAssignmentHistory, LeadStatusHistory
from employes.models import Employee
from customers.models import Customer, CustomerTag
from leads.serializers import (
    LeadSerializer,
    LeadAssignSerializer,
    LeadConvertSerializer,
    LeadAssignmentHistorySerializer,
    LeadStatusHistorySerializer,
)
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsManager, IsTeamLead, IsOrgAdmin


class LeadViewSet(viewsets.ModelViewSet):
    """
    CRUD for Leads with hierarchical pipeline visibility:
    - Org Admin & Manager: See all leads in the organization.
    - Team Lead: Sees leads assigned to their team members.
    - Employee: Sees leads assigned to or created by them.
    """
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'source', 'assigned_to', 'assigned_doc_officer', 'assigned_sales_analyst']
    search_fields = ['contact_name', 'phone', 'email', 'lead_code', 'city']
    ordering_fields = ['created_at', 'expected_amount', 'priority']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user, self.request)
        if not org:
            return Lead.objects.none()

        role_ctx = get_user_role_context(user, self.request)
        level = role_ctx['hierarchy_level']

        base_qs = Lead.objects.filter(organization=org).select_related(
            'assigned_to__user', 'assigned_doc_officer__user', 'assigned_sales_analyst__user', 'created_by__user', 'portal_user'
        )
        department=self.request.query_params.get('department'); team=self.request.query_params.get('team')
        if department: base_qs=base_qs.filter(Q(assigned_to__department_id=department)|Q(assigned_doc_officer__department_id=department)|Q(assigned_sales_analyst__department_id=department))
        if team: base_qs=base_qs.filter(Q(assigned_to__team_id=team)|Q(assigned_doc_officer__team_id=team)|Q(assigned_sales_analyst__team_id=team))

        # Organization admins see the complete organization pipeline.
        if level >= 90:
            return base_qs

        if role_ctx['role_code'] in ('doc_officer','document_verification_officer'):
            employee=getattr(user,'employee',None)
            return base_qs.filter(assigned_doc_officer=employee) if employee else base_qs.none()
        if role_ctx['role_code']=='sales_analyst':
            employee=getattr(user,'employee',None)
            return base_qs.filter(assigned_sales_analyst=employee) if employee else base_qs.none()
        if role_ctx['role_code']=='lead_portal':
            return base_qs.filter(portal_user=user)
        if role_ctx['role_code'] in ('finance_analyst','financial_analyst'):
            return base_qs

        if level >= 70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            departments=manager.managed_departments.all() if manager else []
            return base_qs.filter(Q(assigned_to__department__in=departments)|Q(created_by__department__in=departments)|Q(assigned_doc_officer__department__in=departments)|Q(assigned_sales_analyst__department__in=departments)).distinct()

        # 2. Team Lead: Leads assigned to their team
        if level >= 50:
            tl_qs = getattr(user, 'teamlead_profiles', None)
            if tl_qs and tl_qs.exists():
                tl = tl_qs.first()
                led_teams = tl.teams.values_list('id', flat=True)
                team_employees = Employee.objects.filter(team_id__in=led_teams).values_list('id', flat=True)
                return base_qs.filter(
                    Q(assigned_to_id__in=team_employees) |
                    Q(assigned_doc_officer_id__in=team_employees) |
                    Q(assigned_sales_analyst_id__in=team_employees) |
                    Q(created_by__user=user)
                ).distinct()
            return base_qs.none()

        # 3. Employee: Leads assigned to or created by them
        creator_emp = getattr(user, 'employee', None)
        if creator_emp:
            return base_qs.filter(
                Q(assigned_to=creator_emp) | Q(created_by=creator_emp)
            )

        return base_qs.filter(created_by__user=user)

    def perform_create(self,serializer):
        with transaction.atomic():
            lead=serializer.save()
            LeadStatusHistory.objects.create(lead=lead,old_status='',new_status=lead.status,changed_by=self.request.user,notes='Lead created')
            if lead.assigned_to_id or lead.assigned_doc_officer_id or lead.assigned_sales_analyst_id:
                LeadAssignmentHistory.objects.create(
                    lead=lead, new_owner=lead.assigned_to,
                    new_doc_officer=lead.assigned_doc_officer,
                    new_sales_analyst=lead.assigned_sales_analyst,
                    assigned_by=self.request.user, reason='Initial lead assignment',
                )

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        POST /api/v1/leads/<id>/assign/
        Assigns or reassigns a lead to an employee and logs LeadAssignmentHistory.
        Permitted for: Managers, Team Leads, Org Admins.
        """
        role_ctx = get_user_role_context(request.user, request)
        if role_ctx['hierarchy_level'] < 50:
            return Response(
                {"detail": "Permission denied to assign leads. Only Team Leads, Managers, or Admins can assign leads."},
                status=status.HTTP_403_FORBIDDEN
            )

        lead = self.get_object()
        serializer = LeadAssignSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        emp_id = serializer.validated_data.get('employee_id')
        doc_id = serializer.validated_data.get('document_officer_id')
        sales_id = serializer.validated_data.get('sales_analyst_id')
        reason = serializer.validated_data.get('reason', '')
        assignments={key:Employee.objects.filter(id=value,organization=lead.organization).first() if value else getattr(lead,key) for key,value in (
            ('assigned_to',emp_id),('assigned_doc_officer',doc_id),('assigned_sales_analyst',sales_id)
        )}
        new_owner=assignments['assigned_to']
        if role_ctx['hierarchy_level']<90:
            if role_ctx['hierarchy_level']>=70:
                manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
                departments=manager.managed_departments.all() if manager else []
                allowed=set(departments.values_list('id',flat=True))
                if any(person and person.department_id not in allowed for person in assignments.values()):
                    return Response({'detail':'You can only assign leads to staff in your departments.'},status=403)
            else:
                profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
                teams=profile.teams.all() if profile else []
                allowed=set(teams.values_list('id',flat=True))
                if any(person and person.team_id not in allowed for person in assignments.values()):
                    return Response({'detail':'You can only assign leads to employees in your team.'},status=403)
        old_owner = lead.assigned_to
        old_doc_officer=lead.assigned_doc_officer
        old_sales_analyst=lead.assigned_sales_analyst

        with transaction.atomic():
            lead.assigned_to = new_owner
            lead.assigned_doc_officer=assignments['assigned_doc_officer']
            lead.assigned_sales_analyst=assignments['assigned_sales_analyst']
            lead.save(update_fields=['assigned_to','assigned_doc_officer','assigned_sales_analyst','updated_at'])

            LeadAssignmentHistory.objects.create(
                lead=lead,
                old_owner=old_owner,
                new_owner=new_owner,
                old_doc_officer=old_doc_officer,
                new_doc_officer=lead.assigned_doc_officer,
                old_sales_analyst=old_sales_analyst,
                new_sales_analyst=lead.assigned_sales_analyst,
                assigned_by=request.user,
                reason=reason or f"Assigned to {new_owner.user.get_full_name() or new_owner.user.username}",
            )

        return Response(
            {
                "detail": "Lead staff assignments updated successfully.",
                "lead": LeadSerializer(lead).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='portal-account')
    def portal_account(self, request, pk=None):
        lead=self.get_object()
        if lead.portal_user_id:
            return Response({'detail':'This lead already has a portal account.'},status=409)
        username=str(request.data.get('portal_login','')).strip()
        password=str(request.data.get('portal_password',''))
        from django.contrib.auth import get_user_model
        User=get_user_model()
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        if not username:
            return Response({'portal_login':'A username is required.'},status=400)
        if User.objects.filter(username__iexact=username).exists():
            return Response({'portal_login':'This username is already in use.'},status=400)
        try: validate_password(password)
        except ValidationError as error: return Response({'portal_password':list(error.messages)},status=400)
        with transaction.atomic():
            lead=Lead.objects.select_for_update().get(pk=lead.pk,organization=lead.organization)
            if lead.portal_user_id: return Response({'detail':'This lead already has a portal account.'},status=409)
            lead.portal_user=User.objects.create_user(username=username,email=lead.email,password=password,first_name=lead.contact_name,default_organization=lead.organization)
            lead.save(update_fields=['portal_user'])
        return Response({'detail':'Lead portal account created. Share the login credentials with the lead securely.','portal_username':username},status=201)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """
        POST /api/v1/leads/<id>/convert/
        Converts a qualified lead into an active Customer record.
        """
        lead = self.get_object()
        if lead.converted_customer_id:
            from customers.serializers import CustomerSerializer
            return Response({'detail':'This lead has already been converted.','customer':CustomerSerializer(lead.converted_customer).data},status=200)
        if lead.status != Lead.Status.QUALIFIED:
            return Response(
                {"detail": "Only a qualified lead can be converted to a customer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = LeadConvertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        org = lead.organization

        with transaction.atomic():
            lead=Lead.objects.select_for_update().get(pk=lead.pk,organization=lead.organization)
            if lead.converted_customer_id:
                from customers.serializers import CustomerSerializer
                return Response({'detail':'This lead has already been converted.','customer':CustomerSerializer(lead.converted_customer).data},status=200)
            if lead.status != Lead.Status.QUALIFIED:
                return Response({'detail':'Only a qualified lead can be converted to a customer.'},status=400)
            # 1. Create Customer
            customer_code = f"CUST-{uuid.uuid4().hex[:8].upper()}"
            customer = Customer.objects.create(
                organization=org,
                customer_code=customer_code,
                customer_type=data['customer_type'],
                full_name=lead.contact_name,
                legal_name=data.get('legal_name') or lead.contact_name,
                primary_phone=lead.phone,
                email=lead.email,
                preferred_channel=Customer.PreferredChannel.PHONE,
                address_line1=data.get('address_line1', ''),
                address_line2=data.get('address_line2', ''),
                city=data.get('city') or lead.city,
                state=data.get('state') or lead.state,
                pin_code=data.get('pin_code', ''),
                business_category=data.get('business_category', ''),
                segment=data.get('segment', 'Retail'),
                source=lead.source,
                status=Customer.Status.ACTIVE,
                created_by=lead.assigned_to or lead.created_by,
                assigned_to=lead.assigned_to,
            )

            # 2. Add Customer Tag
            tag_choice = data.get('tag', CustomerTag.Tag.GENERAL)
            CustomerTag.objects.create(
                customer=customer,
                tag=tag_choice,
            )

            # 3. Mark Lead as Qualified
            lead.status = Lead.Status.QUALIFIED
            lead.converted_customer=customer
            lead.save(update_fields=['status','converted_customer','updated_at'])

            from customers.serializers import CustomerSerializer
            return Response(
                {
                    "detail": "Lead successfully converted to Customer.",
                    "customer": CustomerSerializer(customer).data,
                    "lead_id": str(lead.id),
                    "lead_status": lead.status,
                },
                status=status.HTTP_201_CREATED,
            )

    @action(detail=True,methods=['post'])
    def transition(self,request,pk=None):
        lead=self.get_object(); new=request.data.get('status')
        allowed={Lead.Status.NEW:{Lead.Status.CONTACTED,Lead.Status.UNQUALIFIED},Lead.Status.CONTACTED:{Lead.Status.QUALIFIED,Lead.Status.UNQUALIFIED}}
        if lead.converted_customer_id:return Response({'detail':'Converted leads cannot change status.'},status=400)
        if new not in allowed.get(lead.status,set()):return Response({'detail':f'Cannot move from {lead.status} to {new}.'},status=400)
        old=lead.status; lead.status=new
        with transaction.atomic():
            lead.save(update_fields=['status','updated_at'])
            LeadStatusHistory.objects.create(lead=lead,old_status=old,new_status=new,changed_by=request.user,notes=request.data.get('notes',''))
        return Response(LeadSerializer(lead,context={'request':request}).data)

    @action(detail=True,methods=['get'],url_path='status-history')
    def status_history(self,request,pk=None):
        lead=self.get_object(); return Response(LeadStatusHistorySerializer(lead.status_history.select_related('changed_by'),many=True).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        GET /api/v1/leads/<id>/history/
        Returns assignment history audit log for this lead.
        """
        lead = self.get_object()
        history_qs = LeadAssignmentHistory.objects.filter(lead=lead).select_related(
            'old_owner__user', 'new_owner__user', 'assigned_by'
        ).order_by('-assigned_at')
        serializer = LeadAssignmentHistorySerializer(history_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
