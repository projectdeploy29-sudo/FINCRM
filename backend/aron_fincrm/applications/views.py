import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from organizations.tenant import get_user_organization, get_user_role_context
from django.db.models import Q
from permitions.permissions import IsAuthenticatedTenant
from applications.models import FinancialApplication, ApplicationStatusHistory, ApplicationChecklist
from applications.serializers import FinancialApplicationSerializer, ApplicationStatusHistorySerializer, ApplicationChecklistSerializer

ALLOWED = {
 'draft': {'submitted','withdrawn'}, 'submitted': {'under_review','withdrawn'},
 'under_review': {'qualified','unqualified','rejected','withdrawn'},
 'qualified': {'approved','rejected','withdrawn'}, 'unqualified': set(),
 'approved': {'disbursed','withdrawn'}, 'disbursed': {'completed'},
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
        if new == 'disbursed':
            from documents.models import Document
            docs=Document.objects.filter(application=app,organization=app.organization)
            checklist=ApplicationChecklist.objects.filter(application=app)
            if not docs.exists() or docs.exclude(status=Document.Status.ACCEPTED).exists():
                return Response({'detail':'Upload and accept all application documents before disbursement.'},status=400)
            if not checklist.exists() or checklist.exclude(status=ApplicationChecklist.Status.ACCEPTED).exists():
                return Response({'detail':'Complete the application document checklist before disbursement.'},status=400)
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
                if raw_rate not in (None,''):
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
                rate=(app.annual_interest_rate or Decimal('0'))/Decimal('1200')
                if rate:
                    factor=(Decimal('1')+rate)**app.loan_tenure_months
                    app.monthly_repayment_amount=(approved*rate*factor/(factor-1)).quantize(Decimal('0.01'))
                else: app.monthly_repayment_amount=(approved/app.loan_tenure_months).quantize(Decimal('0.01'))
            if new=='disbursed':
                from decimal import Decimal, InvalidOperation
                raw_disbursed=request.data.get('disbursed_amount')
                if raw_disbursed in (None,''): return Response({'detail':'Enter the actual amount disbursed to the customer.'},status=400)
                try: disbursed=Decimal(str(raw_disbursed))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid disbursed_amount.'},status=400)
                if disbursed<=0 or (app.approved_amount and disbursed>app.approved_amount): return Response({'detail':'Disbursed amount must be positive and cannot exceed the approved amount.'},status=400)
                app.disbursed_amount=disbursed
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
        if app.lead_id:
            if app.lead.organization_id != app.organization_id or (app.lead.customer_id and app.lead.customer_id != app.customer_id) or (app.lead.application_id and app.lead.application_id != app.id):
                return Response({'detail':'The existing linked lead does not match this application customer.'},status=409)
            if not app.lead.customer_id or not app.lead.application_id:
                app.lead.customer=app.customer
                app.lead.application=app
                app.lead.save(update_fields=['customer','application','updated_at'])
            return Response({'detail':'This application already has a linked lead.','lead_id':str(app.lead_id),'lead_code':app.lead.lead_code},status=200)
        from leads.models import Lead, LeadStatusHistory, LeadAssignmentHistory
        from leads.serializers import LeadSerializer
        assigned=app.assigned_employee
        if not assigned:
            return Response({'detail':'Assign this application to an employee before converting it to a lead.'},status=400)
        lead_source=app.customer.source.lower().replace(' ','_') if app.customer.source else Lead.Source.OTHER
        if lead_source not in dict(Lead.Source.choices): lead_source=Lead.Source.OTHER
        with transaction.atomic():
            app=FinancialApplication.objects.select_for_update().select_related('customer','assigned_employee','lead').get(pk=app.pk,organization=app.organization)
            if app.lead_id:
                if app.lead.organization_id != app.organization_id or (app.lead.customer_id and app.lead.customer_id != app.customer_id) or (app.lead.application_id and app.lead.application_id != app.id):
                    return Response({'detail':'The existing linked lead does not match this application customer.'},status=409)
                app.lead.customer=app.customer
                app.lead.application=app
                app.lead.save(update_fields=['customer','application','updated_at'])
                return Response({'detail':'This application already has a linked lead.','lead_id':str(app.lead_id),'lead_code':app.lead.lead_code},status=200)
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
            if assigned:
                LeadAssignmentHistory.objects.create(lead=lead,new_owner=assigned,assigned_by=request.user,reason='Assigned from qualified application')
        return Response({'detail':'Qualified application converted to a new lead.','lead':LeadSerializer(lead,context={'request':request}).data},status=201)
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        return Response(ApplicationStatusHistorySerializer(self.get_object().applicationstatushistory_set.order_by('-changed_at'), many=True).data)

class ApplicationChecklistViewSet(viewsets.ModelViewSet):
    serializer_class=ApplicationChecklistSerializer
    permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['application','status']
    def get_permissions(self):
        from permitions.permissions import IsEmployee, IsOrgAdmin
        if self.action in ('create','update','partial_update'): return [IsAuthenticatedTenant(),IsEmployee()]
        if self.action=='destroy': return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return ApplicationChecklist.objects.none()
        qs=ApplicationChecklist.objects.filter(application__organization=org)
        ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
        if level>=90:return qs
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(application__assigned_employee__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(application__assigned_employee__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(application__assigned_employee=employee) if employee else qs.none()
    def perform_create(self, serializer): serializer.save(updated_by=self.request.user)
    def perform_update(self, serializer): serializer.save(updated_by=self.request.user)
