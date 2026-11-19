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
from leads.serializers import (
    LeadSerializer,
    LeadPortalSerializer,
    LeadAssignSerializer,
    LeadAssignmentHistorySerializer,
    LeadStatusHistorySerializer,
)
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin


class LeadViewSet(viewsets.ModelViewSet):
    """
    CRUD for Leads with hierarchical pipeline visibility:
    - Org Admin & Manager: See all leads in the organization.
    - Team Lead: Sees leads assigned to their team members.
    - Employee: Sees leads assigned to them.
    """
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'source', 'assigned_to']
    search_fields = ['contact_name', 'phone', 'email', 'lead_code', 'city']
    ordering_fields = ['created_at', 'expected_amount', 'priority']
    ordering = ['-created_at']

    def get_permissions(self):
        role_ctx=get_user_role_context(self.request.user,self.request)
        if role_ctx['role_code']=='lead_portal':
            if self.action in ('list','retrieve','portal_dashboard'):
                return [IsAuthenticatedTenant()]
            return [IsAuthenticatedTenant(),IsOrgAdmin()]
        if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]

    def get_serializer_class(self):
        if get_user_role_context(self.request.user,self.request)['role_code']=='lead_portal':
            return LeadPortalSerializer
        return LeadSerializer

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user, self.request)
        if not org:
            return Lead.objects.none()

        role_ctx = get_user_role_context(user, self.request)
        level = role_ctx['hierarchy_level']

        base_qs = Lead.objects.filter(organization=org).select_related('assigned_to__user', 'created_by__user', 'portal_user', 'customer', 'application')
        department=self.request.query_params.get('department'); team=self.request.query_params.get('team')
        if department: base_qs=base_qs.filter(assigned_to__department_id=department)
        if team: base_qs=base_qs.filter(assigned_to__team_id=team)

        # Organization admins see the complete organization pipeline.
        if level >= 90:
            return base_qs

        if role_ctx['role_code']=='lead_portal':
            return base_qs.filter(portal_user=user)

        if level >= 70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            departments=manager.managed_departments.all() if manager else []
            return base_qs.filter(assigned_to__department__in=departments)

        # 2. Team Lead: Leads assigned to their team
        if level >= 50:
            tl_qs = getattr(user, 'teamlead_profiles', None)
            if tl_qs and tl_qs.exists():
                tl = tl_qs.first()
                led_teams = tl.teams.values_list('id', flat=True)
                team_employees = Employee.objects.filter(team_id__in=led_teams).values_list('id', flat=True)
                return base_qs.filter(assigned_to_id__in=team_employees)
            return base_qs.none()

        # 3. Employee: Leads assigned to or created by them
        creator_emp = getattr(user, 'employee', None)
        if creator_emp:
            return base_qs.filter(assigned_to=creator_emp)

        return base_qs.filter(created_by__user=user)

    def create(self, request, *args, **kwargs):
        return Response({'detail':'Create and qualify an application, then use its Convert to lead action.'},status=405)

    def perform_create(self,serializer):
        with transaction.atomic():
            lead=serializer.save()
            LeadStatusHistory.objects.create(lead=lead,old_status='',new_status=lead.status,changed_by=self.request.user,notes='Lead created')
            if lead.assigned_to_id:
                LeadAssignmentHistory.objects.create(
                    lead=lead, new_owner=lead.assigned_to,
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
        reason = serializer.validated_data.get('reason', '')
        new_owner=Employee.objects.filter(id=emp_id,organization=lead.organization).first() if emp_id else None
        old_owner = lead.assigned_to

        if old_owner_id := getattr(old_owner, 'id', None):
            if old_owner_id == getattr(new_owner, 'id', None):
                return Response({
                    'detail': 'Lead is already assigned to this employee.',
                    'lead': LeadSerializer(lead, context={'request': request}).data,
                }, status=status.HTTP_200_OK)

        with transaction.atomic():
            lead.assigned_to = new_owner
            lead.save(update_fields=['assigned_to','updated_at'])

            LeadAssignmentHistory.objects.create(
                lead=lead,
                old_owner=old_owner,
                new_owner=new_owner,
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
        if not lead.application_id or lead.application.status not in ('disbursed','completed') or lead.status!=Lead.Status.QUALIFIED:
            return Response({'detail':'Lead login can be created only after the loan has been disbursed and the lead is qualified.'},status=400)
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

    @action(detail=False, methods=['get'], url_path='portal-dashboard')
    def portal_dashboard(self, request):
        if get_user_role_context(request.user,request)['role_code']!='lead_portal':
            return Response({'detail':'This dashboard is only available to lead portal accounts.'},status=403)
        lead=self.get_queryset().select_related('customer','application').first()
        if not lead:
            return Response({'detail':'No lead record is linked to this account.'},status=404)
        from finance.models import RepaymentSchedule, RepaymentPayment
        from tasks.models import CostomerFollowUp, LeadFollowUp, applicationFollowUp
        from django.db.models import Sum
        from django.utils import timezone
        app=lead.application
        schedules=RepaymentSchedule.objects.filter(organization=lead.organization).filter(Q(lead=lead)|Q(application=app)).distinct().order_by('due_date') if app else RepaymentSchedule.objects.filter(organization=lead.organization,lead=lead).order_by('due_date')
        schedule_ids=list(schedules.values_list('id',flat=True))
        payments=RepaymentPayment.objects.filter(organization=lead.organization,repayment_schedule_id__in=schedule_ids).order_by('-payment_date','-created_at')
        verified_paid=payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
        remaining=sum((row.outstanding_amount for row in schedules),0)
        next_schedule=schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']).first()
        upcoming_payments=[{'id':str(row.pk),'installment_number':row.installment_number,'amount':str(row.outstanding_amount),'due_date':row.due_date,'status':row.status} for row in schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']) if row.due_date>=timezone.localdate()]
        overdue_payments=[{'id':str(row.pk),'installment_number':row.installment_number,'amount':str(row.outstanding_amount),'due_date':row.due_date,'status':row.status} for row in schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']) if row.due_date<timezone.localdate()]
        payment_history=[{'id':str(row.pk),'amount':str(row.amount),'payment_date':row.payment_date,'payment_method':row.payment_method,'status':row.verification_status,'transaction_reference':row.transaction_reference or ''} for row in payments]
        followup_rows=[]
        followup_sets=[]
        if lead.customer_id: followup_sets.append(CostomerFollowUp.objects.filter(organization=lead.organization,customer_id=lead.customer_id))
        followup_sets.append(LeadFollowUp.objects.filter(organization=lead.organization,lead=lead))
        if app: followup_sets.append(applicationFollowUp.objects.filter(organization=lead.organization,application=app))
        for queryset in followup_sets:
            for item in queryset.order_by('-scheduled_at'):
                followup_rows.append({'id':str(item.pk),'title':item.title or item.followup_type.title(),'description':item.description,'purpose':item.purpose,'type':item.followup_type,'scheduled_at':item.scheduled_at,'status':item.status,'remarks':item.notes or '', 'outcome':item.outcome or '', 'completed_at':item.completed_at})
        followup_rows.sort(key=lambda row:row['scheduled_at'],reverse=True)
        return Response({
            'lead':LeadPortalSerializer(lead,context={'request':request}).data,
            'loan':{
                'approved_amount':str(app.approved_amount) if app and app.approved_amount is not None else None,
                'disbursed_amount':str(app.disbursed_amount) if app and app.disbursed_amount is not None else None,
                'disbursed_at':app.disbursed_at if app else None,
                'annual_interest_rate':str(app.annual_interest_rate) if app and app.annual_interest_rate is not None else None,
                'tenure_months':app.loan_tenure_months if app else None,
                'monthly_repayment_amount':str(app.monthly_repayment_amount) if app and app.monthly_repayment_amount is not None else None,
                'next_payment_due_date':next_schedule.due_date if next_schedule else (app.next_payment_due_date if app else None),
                'total_paid':str(verified_paid),'remaining_balance':str(remaining),
            },
            'completed_payments':[row for row in payment_history if row['status']=='VERIFIED'],
            'upcoming_payments':upcoming_payments,'overdue_payments':overdue_payments,'payment_history':payment_history,
            'upcoming_followups':[row for row in followup_rows if row['status']=='PENDING'],
            'completed_followups':[row for row in followup_rows if row['status']=='COMPLETED'],
        })

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        return Response({'detail':'Lead-to-customer conversion is disabled. Leads are created from qualified applications.'},status=410)

    @action(detail=True,methods=['post'])
    def transition(self,request,pk=None):
        lead=self.get_object(); new=request.data.get('status')
        allowed={Lead.Status.NEW:{Lead.Status.CONTACTED},Lead.Status.CONTACTED:{Lead.Status.QUALIFIED}}
        if lead.converted_customer_id:return Response({'detail':'Converted leads cannot change status.'},status=400)
        if new == Lead.Status.QUALIFIED and (not lead.application_id or lead.application.status not in ('disbursed','completed') or not lead.application.disbursed_amount or not lead.application.repayment_schedules.exists()):
            return Response({'detail':'A lead can be marked Qualified only after the loan is disbursed and its repayment schedule is created.'},status=400)
        if new not in allowed.get(lead.status,set()):return Response({'detail':f'Cannot move from {lead.status} to {new}.'},status=400)
        old=lead.status; lead.status=new
        with transaction.atomic():
            lead.save(update_fields=['status','updated_at'])
            LeadStatusHistory.objects.create(lead=lead,old_status=old,new_status=new,changed_by=request.user,notes=request.data.get('notes',''))
        return Response(LeadSerializer(lead,context={'request':request}).data)

    @action(detail=True,methods=['get'],url_path='status-history')
    def status_history(self,request,pk=None):
        lead=self.get_object(); return Response(LeadStatusHistorySerializer(lead.status_history.select_related('changed_by').order_by('-changed_at'),many=True).data)

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
