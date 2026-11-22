import uuid
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from organizations.tenant import get_user_organization, get_user_role_context
from django.db.models import Q
from permitions.permissions import IsAuthenticatedTenant
from applications.models import FinancialApplication, ApplicationStatusHistory
from applications.serializers import FinancialApplicationSerializer, ApplicationStatusHistorySerializer

ALLOWED = {
 'draft': {'submitted','withdrawn'}, 'submitted': {'under_review','withdrawn'},
 'under_review': {'qualified','unqualified','rejected','withdrawn'},
 'qualified': {'rejected','withdrawn'}, 'unqualified': set(),
 'approved': {'withdrawn'}, 'disbursed': {'completed'},
 'rejected': set(), 'completed': set(), 'withdrawn': set(),
}
class FinancialApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = FinancialApplicationSerializer
    permission_classes = [IsAuthenticatedTenant]
    filterset_fields = ['customer','assigned_employee']
    search_fields = ['application_code','customer__full_name']
    ordering_fields = ['created_at','requested_amount','status']
    ordering = ['-created_at', 'id']
    def get_permissions(self):
        from permitions.permissions import IsOrgAdmin
        if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]
    def get_queryset(self):
        org = get_user_organization(self.request.user, self.request)
        if not org: return FinancialApplication.objects.none()
        qs=FinancialApplication.objects.filter(organization=org).select_related('customer','assigned_employee__user')
        department=self.request.query_params.get('department'); team=self.request.query_params.get('team')
        if department: qs=qs.filter(assigned_employee__department_id=department)
        if team: qs=qs.filter(assigned_employee__team_id=team)
        status_filter=self.request.query_params.get('status')
        if status_filter=='pending': qs=qs.filter(status__in=['draft','submitted','under_review'])
        elif status_filter: qs=qs.filter(status=status_filter)
        if self.request.query_params.get('without_repayment_schedule', '').lower() == 'true':
            qs = qs.filter(repayment_schedules__isnull=True).distinct()
        ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
        if level>=90: return qs
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None
            depts=manager.managed_departments.all() if manager else []
            return qs.filter(Q(assigned_employee__department__in=depts)|Q(assigned_employee__manager__user=user))
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
            teams=profile.teams.all() if profile else []
            return qs.filter(assigned_employee__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(assigned_employee=employee) if employee else qs.none()
    def perform_create(self, serializer):
        app=serializer.save()
        ApplicationStatusHistory.objects.create(application=app,old_status='',new_status=app.status,changed_by=self.request.user,notes='Application created')
    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        app = self.get_object(); new = request.data.get('status'); role = get_user_role_context(request.user, request)
        if new not in dict(FinancialApplication.Status.choices): return Response({'detail':'Unknown status.'}, status=400)
        if new not in ALLOWED.get(app.status, set()): return Response({'detail':f'Cannot move from {app.status} to {new}.'}, status=400)
        if new=='under_review' and role['hierarchy_level']<30:return Response({'detail':'A staff member in the application reporting scope must review it.'},status=403)
        if new in ('approved','rejected','disbursed') and role['hierarchy_level']<30:
            return Response({'detail':'A staff member assigned to this application must review it.'}, status=403)
        if new == 'disbursed' and app.status != 'approved': return Response({'detail':'Application must be approved first.'}, status=400)
        if new == 'approved' and not app.lead_id:
            return Response({'detail':'Convert the qualified application to a lead before approving its loan.'},status=400)
        with transaction.atomic():
            old=app.status; app.status=new
            if new=='approved':
                from decimal import Decimal, InvalidOperation
                raw=request.data.get('approved_amount')
                if raw in (None,''): return Response({'detail':'Enter the amount the organization approved after its financial assessment.'},status=400)
                try: approved=Decimal(str(raw))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid approved_amount.'},status=400)
                if approved<=0 or (app.requested_amount and approved>app.requested_amount): return Response({'detail':'Approved amount must be positive and cannot exceed the requested amount.'},status=400)
                app.approved_amount=approved
                raw_rate=request.data.get('annual_interest_rate',app.annual_interest_rate)
                raw_tenure=request.data.get('loan_tenure_months',app.loan_tenure_months)
                if raw_rate in (None,''): return Response({'detail':'Enter the annual interest rate. Enter 0 for an interest-free loan.'},status=400)
                try: rate=Decimal(str(raw_rate))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid annual_interest_rate.'},status=400)
                if rate<0 or rate>100: return Response({'detail':'annual_interest_rate must be between 0 and 100.'},status=400)
                app.annual_interest_rate=rate
                if raw_tenure in (None,''):
                    return Response({'detail':'Enter the approved loan tenure in months.'},status=400)
                try: tenure=int(raw_tenure)
                except (TypeError,ValueError): return Response({'detail':'loan_tenure_months must be a positive whole number.'},status=400)
                if tenure<1 or tenure>600: return Response({'detail':'loan_tenure_months must be between 1 and 600.'},status=400)
                app.loan_tenure_months=tenure
                method=request.data.get('interest_calculation_method',app.interest_calculation_method)
                if method not in dict(FinancialApplication.InterestCalculationMethod.choices):
                    return Response({'detail':'Choose a supported interest calculation method.'},status=400)
                app.interest_calculation_method=method
            if new=='disbursed':
                from decimal import Decimal, InvalidOperation
                raw_rate=request.data.get('annual_interest_rate',app.annual_interest_rate)
                if raw_rate in (None,''): return Response({'detail':'Enter the annual interest rate. Enter 0 for an interest-free loan.'},status=400)
                try: rate=Decimal(str(raw_rate))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid annual_interest_rate.'},status=400)
                if rate<0 or rate>100: return Response({'detail':'annual_interest_rate must be between 0 and 100.'},status=400)
                raw_tenure=request.data.get('loan_tenure_months',app.loan_tenure_months)
                try: tenure=int(raw_tenure)
                except (TypeError,ValueError): return Response({'detail':'Enter the approved loan tenure in months.'},status=400)
                if tenure<1 or tenure>600: return Response({'detail':'loan_tenure_months must be between 1 and 600.'},status=400)
                method=request.data.get('interest_calculation_method',app.interest_calculation_method)
                if method not in dict(FinancialApplication.InterestCalculationMethod.choices):
                    return Response({'detail':'Choose a supported interest calculation method.'},status=400)
                raw_disbursed=request.data.get('disbursed_amount')
                if raw_disbursed in (None,''): return Response({'detail':'Enter the interest-bearing loan principal disbursed.'},status=400)
                try: disbursed=Decimal(str(raw_disbursed))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid disbursed_amount.'},status=400)
                if disbursed<=0 or not app.approved_amount or disbursed>app.approved_amount: return Response({'detail':'Loan principal must be positive and cannot exceed the approved amount.'},status=400)
                raw_deductions=request.data.get('upfront_deductions_amount',0)
                try: deductions=Decimal(str(raw_deductions or 0))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid upfront_deductions_amount.'},status=400)
                if deductions<0 or deductions>=disbursed: return Response({'detail':'Upfront deductions must be zero or more and lower than the loan principal.'},status=400)
                app.disbursed_amount=disbursed
                app.upfront_deductions_amount=deductions
                app.net_disbursed_amount=disbursed-deductions
                app.annual_interest_rate=rate
                app.loan_tenure_months=tenure
                app.interest_calculation_method=method
                app.disbursed_at=timezone.now()
            if new=='submitted': app.submitted_at=timezone.now()
            if new=='completed': app.completed_at=timezone.now()
            app.save()
            ApplicationStatusHistory.objects.create(application=app,old_status=old,new_status=new,changed_by=request.user,notes=request.data.get('notes',''))
        return Response(self.get_serializer(app).data)

    @action(detail=True, methods=['post'], url_path='convert-to-lead')
    def convert_to_lead(self, request, pk=None):
        app=self.get_object()
        if app.status != FinancialApplication.Status.QUALIFIED:
            return Response({'detail':'Only a qualified application can be converted to a lead.'},status=400)
        from leads.models import Lead, LeadStatusHistory, LeadAssignmentHistory
        from leads.serializers import LeadSerializer
        try:
            with transaction.atomic():
                app=FinancialApplication.objects.select_for_update().select_related('customer','assigned_employee','lead').get(pk=app.pk,organization=app.organization)
                if app.status != FinancialApplication.Status.QUALIFIED:
                    return Response({'detail':'Only a qualified application can be converted to a lead.'},status=400)
                if app.lead_id:
                    lead=app.lead
                    if lead.organization_id != app.organization_id or (lead.customer_id and lead.customer_id != app.customer_id) or (lead.application_id and lead.application_id != app.id):
                        return Response({'detail':'The existing linked lead does not match this application customer.'},status=409)
                    lead.customer=app.customer
                    lead.application=app
                    lead.save(update_fields=['customer','application','updated_at'])
                    return Response({'detail':'This application already has a linked lead.','lead_id':str(lead.id),'lead_code':lead.lead_code},status=200)
                assigned=app.assigned_employee
                if not assigned:
                    return Response({'detail':'Assign this application to an employee before converting it to a lead.'},status=400)
                if assigned.employment_status != assigned.EmploymentStatus.ACTIVE:
                    return Response({'detail':'Reassign this application to an active employee before converting it to a lead.'},status=400)
                from subscriptions.entitlements import enforce_resource_limit
                enforce_resource_limit(app.organization, 'leads', lock=True)
                lead_source=app.customer.source.lower().replace(' ','_') if app.customer.source else Lead.Source.OTHER
                if lead_source not in dict(Lead.Source.choices): lead_source=Lead.Source.OTHER
                lead=Lead.objects.create(
                    organization=app.organization, lead_code=f'LEAD-{uuid.uuid4().hex[:8].upper()}',
                    contact_name=app.customer.full_name or app.customer.legal_name,
                    phone=app.customer.primary_phone, email=app.customer.email,
                    city=app.customer.city, state=app.customer.state,
                    assigned_to=assigned, created_by=assigned,
                    customer=app.customer, application=app, source=lead_source,
                    expected_amount=app.requested_amount, currency=app.currency,
                    status=Lead.Status.NEW,
                )
                app.lead=lead
                app.save(update_fields=['lead','updated_at'])
                LeadStatusHistory.objects.create(lead=lead,old_status='',new_status=Lead.Status.NEW,changed_by=request.user,notes='Created from qualified application')
                LeadAssignmentHistory.objects.create(lead=lead,new_owner=assigned,assigned_by=request.user,reason='Assigned from qualified application')
        except IntegrityError:
            # The OneToOne application constraint is the final concurrency guard.
            # If another request won, return its lead instead of creating a duplicate.
            lead=Lead.objects.filter(organization=app.organization,application_id=app.id).first()
            if not lead or lead.customer_id != app.customer_id:
                return Response({'detail':'Application conversion conflicted with another update.'},status=409)
            return Response({'detail':'This application already has a linked lead.','lead_id':str(lead.id),'lead_code':lead.lead_code},status=200)
        return Response({'detail':'Qualified application converted to a new lead.','lead':LeadSerializer(lead,context={'request':request}).data},status=201)
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        return Response(ApplicationStatusHistorySerializer(self.get_object().applicationstatushistory_set.order_by('-changed_at'), many=True).data)
