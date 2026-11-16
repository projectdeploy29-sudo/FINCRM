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
 'under_review': {'approved','rejected','withdrawn'}, 'approved': {'disbursed','withdrawn'},
 'disbursed': {'completed'}, 'rejected': set(), 'completed': set(), 'withdrawn': set(),
}
class FinancialApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = FinancialApplicationSerializer
    permission_classes = [IsAuthenticatedTenant]
    filterset_fields = ['customer','assigned_employee']
    search_fields = ['application_code','customer__full_name']
    ordering_fields = ['created_at','requested_amount','status']
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
        if ctx['role_code'] in ('doc_officer','document_verification_officer'):
            employee=getattr(user,'employee',None)
            return qs.filter(lead__assigned_doc_officer=employee) if employee else qs.none()
        if ctx['role_code']=='sales_analyst':
            employee=getattr(user,'employee',None)
            return qs.filter(lead__assigned_sales_analyst=employee) if employee else qs.none()
        if ctx['role_code'] in ('finance_analyst','financial_analyst'): return qs
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
        code=role['role_code']; allowed_review_roles=('org_admin','manager','super_admin','finance_analyst','financial_analyst')
        review_roles=(*allowed_review_roles,'doc_officer','document_verification_officer')
        if new=='under_review' and code not in review_roles:return Response({'detail':'A manager, finance analyst, or document verification officer must review applications.'},status=403)
        if new in ('approved','rejected','disbursed') and code not in allowed_review_roles:
            return Response({'detail':'Finance approval is required.'}, status=403)
        if new == 'disbursed' and app.status != 'approved': return Response({'detail':'Application must be approved first.'}, status=400)
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
                raw=request.data.get('approved_amount') or app.requested_amount
                try: approved=Decimal(str(raw))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid approved_amount.'},status=400)
                if approved<=0 or (app.requested_amount and approved>app.requested_amount): return Response({'detail':'Approved amount must be positive and cannot exceed the requested amount.'},status=400)
                app.approved_amount=approved
            if new=='disbursed':
                from decimal import Decimal, InvalidOperation
                try: disbursed=Decimal(str(request.data.get('disbursed_amount') or app.approved_amount))
                except (InvalidOperation,TypeError): return Response({'detail':'Provide a valid disbursed_amount.'},status=400)
                if disbursed<=0 or (app.approved_amount and disbursed>app.approved_amount): return Response({'detail':'Disbursed amount must be positive and cannot exceed the approved amount.'},status=400)
                app.disbursed_amount=disbursed
            if new=='submitted': app.submitted_at=timezone.now()
            if new=='completed': app.completed_at=timezone.now()
            app.save()
            ApplicationStatusHistory.objects.create(application=app,old_status=old,new_status=new,changed_by=request.user,notes=request.data.get('notes',''))
        return Response(self.get_serializer(app).data)
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        return Response(ApplicationStatusHistorySerializer(self.get_object().applicationstatushistory_set.order_by('-changed_at'), many=True).data)

class ApplicationChecklistViewSet(viewsets.ModelViewSet):
    serializer_class=ApplicationChecklistSerializer
    permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['application','status']
    def get_permissions(self):
        from permitions.permissions import IsDocumentVerificationOfficer, IsOrgAdmin
        if self.action in ('create','update','partial_update'): return [IsAuthenticatedTenant(),IsDocumentVerificationOfficer()]
        if self.action=='destroy': return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return ApplicationChecklist.objects.none()
        qs=ApplicationChecklist.objects.filter(application__organization=org)
        ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
        if level>=90 or ctx['role_code'] in ('finance_analyst','financial_analyst'):return qs
        if ctx['role_code'] in ('doc_officer','document_verification_officer'):
            employee=getattr(user,'employee',None)
            return qs.filter(application__lead__assigned_doc_officer=employee) if employee else qs.none()
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
