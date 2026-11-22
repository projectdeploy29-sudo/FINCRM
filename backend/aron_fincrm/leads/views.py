from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
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
        from organizations.dates import organization_local_date
        app=lead.application
        schedules=RepaymentSchedule.objects.filter(organization=lead.organization).filter(Q(lead=lead)|Q(application=app)).distinct().order_by('due_date') if app else RepaymentSchedule.objects.filter(organization=lead.organization,lead=lead).order_by('due_date')
        schedule_ids=list(schedules.values_list('id',flat=True))
        payments=RepaymentPayment.objects.filter(organization=lead.organization,repayment_schedule_id__in=schedule_ids).order_by('-payment_date','-created_at')
        verified_paid=payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
        remaining=sum((row.outstanding_amount for row in schedules),0)
        schedule_totals=schedules.aggregate(total_interest=Sum('interest_due'),total_repayment=Sum('expected_amount'))
        next_schedule=schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']).first()
        local_today=organization_local_date(request)
        upcoming_payments=[{'id':str(row.pk),'installment_number':row.installment_number,'amount':str(row.outstanding_amount),'principal_due':str(row.principal_due) if row.principal_due is not None else None,'interest_due':str(row.interest_due) if row.interest_due is not None else None,'due_date':row.due_date,'status':row.status} for row in schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']) if row.due_date>=local_today]
        overdue_payments=[{'id':str(row.pk),'installment_number':row.installment_number,'amount':str(row.outstanding_amount),'principal_due':str(row.principal_due) if row.principal_due is not None else None,'interest_due':str(row.interest_due) if row.interest_due is not None else None,'due_date':row.due_date,'status':row.status} for row in schedules.exclude(status__in=['PAID','WAIVED','CANCELLED']) if row.due_date<local_today]
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
                'net_disbursed_amount':str(app.net_disbursed_amount) if app and app.net_disbursed_amount is not None else None,
                'upfront_deductions_amount':str(app.upfront_deductions_amount) if app else None,
                'disbursed_at':app.disbursed_at if app else None,
                'annual_interest_rate':str(app.annual_interest_rate) if app and app.annual_interest_rate is not None else None,
                'interest_calculation_method':app.interest_calculation_method if app else None,
                'tenure_months':app.loan_tenure_months if app else None,
                'monthly_repayment_amount':str(app.monthly_repayment_amount) if app and app.monthly_repayment_amount is not None else None,
                'total_scheduled_interest':str(schedule_totals['total_interest']) if schedule_totals['total_interest'] is not None else None,
                'total_scheduled_repayment':str(schedule_totals['total_repayment']) if schedule_totals['total_repayment'] is not None else None,
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

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        from applications.models import ApplicationStatusHistory, FinancialApplication

        lead = self.get_object()
        new = request.data.get('status')
        allowed = {
            Lead.Status.NEW: {Lead.Status.CONTACTED},
            Lead.Status.CONTACTED: {Lead.Status.APPROVED},
            Lead.Status.APPROVED: {Lead.Status.DISBURSED},
            Lead.Status.DISBURSED: {Lead.Status.QUALIFIED},
        }
        if lead.converted_customer_id:
            return Response({'detail': 'Converted leads cannot change status.'}, status=400)
        if new not in allowed.get(lead.status, set()):
            return Response({'detail': f'Cannot move from {lead.status} to {new}.'}, status=400)

        if new == Lead.Status.QUALIFIED:
            application = lead.application if lead.application_id else None
            if (
                not application
                or application.status not in (FinancialApplication.Status.DISBURSED, FinancialApplication.Status.COMPLETED)
                or not application.disbursed_amount
                or not application.repayment_schedules.exists()
            ):
                return Response({
                    'detail': 'Generate a repayment schedule for the disbursed application before marking this lead Qualified.'
                }, status=400)

        notes = str(request.data.get('notes', '') or '')
        with transaction.atomic():
            lead = Lead.objects.select_for_update().select_related('application').get(
                pk=lead.pk, organization=lead.organization,
            )
            old_lead_status = lead.status

            if new in (Lead.Status.APPROVED, Lead.Status.DISBURSED):
                role = get_user_role_context(request.user, request)
                if role['hierarchy_level'] < 30:
                    return Response({'detail': 'A staff account is required to approve or disburse the linked application.'}, status=403)
                if not lead.application_id:
                    return Response({'detail': 'This lead has no linked application.'}, status=400)
                application = FinancialApplication.objects.select_for_update().filter(
                    pk=lead.application_id, organization=lead.organization,
                ).first()
                if not application or application.lead_id != lead.id:
                    return Response({'detail': 'The linked application does not match this lead.'}, status=400)

                if new == Lead.Status.APPROVED:
                    if application.status == FinancialApplication.Status.QUALIFIED:
                        raw_approved = request.data.get('approved_amount')
                        if raw_approved in (None, ''):
                            return Response({'detail': 'Enter the amount approved for this loan.'}, status=400)
                        try:
                            approved_amount = Decimal(str(raw_approved))
                        except (InvalidOperation, TypeError):
                            return Response({'detail': 'Provide a valid approved_amount.'}, status=400)
                        if approved_amount <= 0 or (application.requested_amount and approved_amount > application.requested_amount):
                            return Response({'detail': 'Approved amount must be positive and cannot exceed the requested amount.'}, status=400)

                        raw_rate = request.data.get('annual_interest_rate')
                        if raw_rate in (None, ''):
                            return Response({'detail': 'Enter the annual interest rate. Enter 0 for an interest-free loan.'}, status=400)
                        try:
                            annual_rate = Decimal(str(raw_rate))
                        except (InvalidOperation, TypeError):
                            return Response({'detail': 'Provide a valid annual_interest_rate.'}, status=400)
                        if annual_rate < 0 or annual_rate > 100:
                            return Response({'detail': 'annual_interest_rate must be between 0 and 100.'}, status=400)

                        raw_tenure = request.data.get('loan_tenure_months')
                        if raw_tenure in (None, ''):
                            return Response({'detail': 'Enter the approved loan tenure in months.'}, status=400)
                        try:
                            tenure = int(raw_tenure)
                        except (TypeError, ValueError):
                            return Response({'detail': 'loan_tenure_months must be a positive whole number.'}, status=400)
                        if tenure < 1 or tenure > 600:
                            return Response({'detail': 'loan_tenure_months must be between 1 and 600.'}, status=400)
                        interest_method = request.data.get('interest_calculation_method')
                        if interest_method not in dict(FinancialApplication.InterestCalculationMethod.choices):
                            return Response({'detail': 'Choose a supported interest calculation method.'}, status=400)

                        old_application_status = application.status
                        application.status = FinancialApplication.Status.APPROVED
                        application.approved_amount = approved_amount
                        application.annual_interest_rate = annual_rate
                        application.loan_tenure_months = tenure
                        application.interest_calculation_method = interest_method
                        application.save(update_fields=[
                            'status', 'approved_amount', 'annual_interest_rate',
                            'loan_tenure_months', 'interest_calculation_method', 'updated_at',
                        ])
                        ApplicationStatusHistory.objects.create(
                            application=application,
                            old_status=old_application_status,
                            new_status=application.status,
                            changed_by=request.user,
                            notes=notes,
                        )
                    elif application.status != FinancialApplication.Status.APPROVED:
                        return Response({'detail': 'Move the linked application to Qualified before approving it.'}, status=400)
                    elif (
                        not application.approved_amount
                        or application.annual_interest_rate is None
                        or not application.loan_tenure_months
                    ):
                        return Response({'detail': 'Complete the approved loan terms on the linked application first.'}, status=400)

                else:
                    if application.status == FinancialApplication.Status.APPROVED:
                        approved_amount = application.approved_amount
                        annual_rate = application.annual_interest_rate
                        tenure = application.loan_tenure_months
                        interest_method = application.interest_calculation_method
                        if approved_amount is None or approved_amount <= 0:
                            return Response({'detail': 'Record a positive approved loan amount before disbursement.'}, status=400)
                        if annual_rate is None or annual_rate < 0 or annual_rate > 100:
                            return Response({'detail': 'Set a valid annual interest rate on the approved application.'}, status=400)
                        if not tenure or tenure < 1 or tenure > 600:
                            return Response({'detail': 'Set the approved loan tenure before disbursement.'}, status=400)
                        if interest_method not in dict(FinancialApplication.InterestCalculationMethod.choices):
                            return Response({'detail': 'Choose a supported interest calculation method.'}, status=400)

                        raw_disbursed = request.data.get('disbursed_amount')
                        if raw_disbursed in (None, ''):
                            return Response({'detail': 'Enter the interest-bearing loan principal disbursed.'}, status=400)
                        try:
                            disbursed_amount = Decimal(str(raw_disbursed))
                        except (InvalidOperation, TypeError):
                            return Response({'detail': 'Provide a valid disbursed_amount.'}, status=400)
                        if disbursed_amount <= 0 or disbursed_amount > approved_amount:
                            return Response({'detail': 'Loan principal must be positive and cannot exceed the approved amount.'}, status=400)

                        raw_deductions = request.data.get('upfront_deductions_amount', 0)
                        try:
                            deductions = Decimal(str(raw_deductions or 0))
                        except (InvalidOperation, TypeError):
                            return Response({'detail': 'Provide a valid upfront_deductions_amount.'}, status=400)
                        if deductions < 0 or deductions >= disbursed_amount:
                            return Response({'detail': 'Upfront deductions must be zero or more and lower than the loan principal.'}, status=400)

                        old_application_status = application.status
                        application.status = FinancialApplication.Status.DISBURSED
                        application.disbursed_amount = disbursed_amount
                        application.upfront_deductions_amount = deductions
                        application.net_disbursed_amount = disbursed_amount - deductions
                        application.disbursed_at = timezone.now()
                        application.save(update_fields=[
                            'status', 'disbursed_amount', 'upfront_deductions_amount',
                            'net_disbursed_amount', 'disbursed_at', 'updated_at',
                        ])
                        ApplicationStatusHistory.objects.create(
                            application=application,
                            old_status=old_application_status,
                            new_status=application.status,
                            changed_by=request.user,
                            notes=notes,
                        )
                    elif application.status not in (FinancialApplication.Status.DISBURSED, FinancialApplication.Status.COMPLETED):
                        return Response({'detail': 'Approve the linked application before disbursing it.'}, status=400)
                    elif not application.disbursed_amount:
                        return Response({'detail': 'The application has no recorded disbursed amount.'}, status=400)

            lead.status = new
            lead.save(update_fields=['status', 'updated_at'])
            LeadStatusHistory.objects.create(
                lead=lead, old_status=old_lead_status, new_status=new,
                changed_by=request.user, notes=notes,
            )
        return Response(LeadSerializer(lead, context={'request': request}).data)

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
