import uuid
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from customers.models import Customer
from employes.models import Employee
from finance.models import RepaymentSchedule, RepaymentPayment
from leads.models import Lead, LeadAssignmentHistory, LeadStatusHistory
from leads.serializers import LeadSerializer, LeadPortalSerializer, LeadAssignSerializer, LeadAssignmentHistorySerializer, LeadStatusHistorySerializer
from organizations.tenant import get_user_organization, get_user_role_context
from organizations.dates import organization_local_date
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin


class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticatedTenant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'source', 'assigned_to']
    search_fields = ['contact_name', 'phone', 'email', 'lead_code', 'city']
    ordering_fields = ['created_at', 'expected_amount', 'priority']
    ordering = ['-created_at']

    def get_permissions(self):
        role = get_user_role_context(self.request.user, self.request)['role_code']
        if role == 'lead_portal':
            if self.action in ('list', 'retrieve', 'portal_dashboard'):
                return [IsAuthenticatedTenant()]
            return [IsAuthenticatedTenant(), IsOrgAdmin()]
        if self.action == 'destroy':
            return [IsAuthenticatedTenant(), IsOrgAdmin()]
        return [IsAuthenticatedTenant()]

    def get_serializer_class(self):
        if get_user_role_context(self.request.user, self.request)['role_code'] == 'lead_portal':
            return LeadPortalSerializer
        return LeadSerializer

    def get_queryset(self):
        user = self.request.user
        org = get_user_organization(user, self.request)
        if not org:
            return Lead.objects.none()
        ctx = get_user_role_context(user, self.request)
        level = ctx['hierarchy_level']
        qs = Lead.objects.filter(organization=org).select_related('assigned_to__user', 'created_by__user', 'portal_user', 'customer')
        if self.request.query_params.get('without_repayment_schedule') == 'true':
            qs = qs.filter(repayment_schedules__isnull=True)
        department = self.request.query_params.get('department')
        team = self.request.query_params.get('team')
        if department:
            qs = qs.filter(assigned_to__department_id=department)
        if team:
            qs = qs.filter(assigned_to__team_id=team)
        if level >= 90:
            return qs
        if ctx['role_code'] == 'lead_portal':
            return qs.filter(portal_user=user)
        if level >= 70:
            manager = user.manager_set.first() if hasattr(user, 'manager_set') else None
            depts = manager.managed_departments.all() if manager else []
            return qs.filter(assigned_to__department__in=depts)
        if level >= 50:
            profiles = getattr(user, 'teamlead_profiles', None)
            if profiles and profiles.exists():
                teams = profiles.first().teams.values_list('id', flat=True)
                return qs.filter(assigned_to__team_id__in=teams)
            return qs.none()
        employee = getattr(user, 'employee', None)
        return qs.filter(assigned_to=employee) if employee else qs.filter(created_by__user=user)

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Create a customer and convert it after review to create a lead.'}, status=405)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        if get_user_role_context(request.user, request)['hierarchy_level'] < 50:
            return Response({'detail': 'Only Team Leads, Managers, or Admins can assign leads.'}, status=403)
        lead = self.get_object()
        serializer = LeadAssignSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        employee_id = serializer.validated_data.get('employee_id')
        new_owner = Employee.objects.filter(id=employee_id, organization=lead.organization).first() if employee_id else None
        old_owner = lead.assigned_to
        if old_owner == new_owner:
            return Response({'detail': 'Lead is already assigned to this employee.', 'lead': LeadSerializer(lead).data})
        with transaction.atomic():
            lead.assigned_to = new_owner
            lead.save(update_fields=['assigned_to', 'updated_at'])
            LeadAssignmentHistory.objects.create(lead=lead, old_owner=old_owner, new_owner=new_owner, assigned_by=request.user, reason=serializer.validated_data.get('reason', ''))
        return Response({'detail': 'Lead assignment updated.', 'lead': LeadSerializer(lead).data})

    @action(detail=False, methods=['get'], url_path='portal-dashboard')
    def portal_dashboard(self, request):
        if get_user_role_context(request.user, request)['role_code'] != 'lead_portal':
            return Response({'detail': 'This dashboard is only available to lead portal accounts.'}, status=403)
        lead = self.get_queryset().select_related('customer').first()
        if not lead:
            return Response({'detail': 'No lead record is linked to this account.'}, status=404)
        schedules = RepaymentSchedule.objects.filter(organization=lead.organization, lead=lead).order_by('due_date')
        schedule_ids = list(schedules.values_list('id', flat=True))
        payments = RepaymentPayment.objects.filter(organization=lead.organization, repayment_schedule_id__in=schedule_ids).order_by('-payment_date', '-created_at')
        verified_paid = payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
        remaining = sum((row.outstanding_amount for row in schedules), 0)
        totals = schedules.aggregate(total_interest=Sum('interest_due'), total_repayment=Sum('expected_amount'))
        next_schedule = schedules.exclude(status__in=['PAID', 'WAIVED', 'CANCELLED']).first()
        today = organization_local_date(request)
        def schedule_row(row):
            return {'id': str(row.pk), 'installment_number': row.installment_number, 'amount': str(row.outstanding_amount), 'principal_due': str(row.principal_due) if row.principal_due is not None else None, 'interest_due': str(row.interest_due) if row.interest_due is not None else None, 'due_date': row.due_date, 'status': row.status}
        upcoming = [schedule_row(row) for row in schedules.exclude(status__in=['PAID', 'WAIVED', 'CANCELLED']) if row.due_date >= today]
        overdue = [schedule_row(row) for row in schedules.exclude(status__in=['PAID', 'WAIVED', 'CANCELLED']) if row.due_date < today]
        history = [{'id': str(row.id), 'amount': str(row.amount), 'payment_date': row.payment_date, 'payment_method': row.payment_method, 'status': row.verification_status, 'transaction_reference': row.transaction_reference or ''} for row in payments]
        from tasks.models import CostomerFollowUp, LeadFollowUp
        followups = []
        for qs in (CostomerFollowUp.objects.filter(organization=lead.organization, customer_id=lead.customer_id) if lead.customer_id else CostomerFollowUp.objects.none(), LeadFollowUp.objects.filter(organization=lead.organization, lead=lead)):
            for item in qs.order_by('-scheduled_at'):
                followups.append({'id': str(item.pk), 'title': item.title or item.followup_type.title(), 'description': item.description, 'purpose': item.purpose, 'type': item.followup_type, 'scheduled_at': item.scheduled_at, 'status': item.status, 'remarks': item.notes or '', 'outcome': item.outcome or ''})
        followups.sort(key=lambda item: item['scheduled_at'], reverse=True)
        return Response({'lead': LeadPortalSerializer(lead, context={'request': request}).data, 'loan': {
            'approved_amount': str(lead.approved_amount) if lead.approved_amount is not None else None,
            'disbursed_amount': str(lead.disbursed_amount) if lead.disbursed_amount is not None else None,
            'net_disbursed_amount': str(lead.net_disbursed_amount) if lead.net_disbursed_amount is not None else None,
            'upfront_deductions_amount': str(lead.upfront_deductions_amount), 'disbursed_at': lead.disbursed_at,
            'annual_interest_rate': str(lead.annual_interest_rate) if lead.annual_interest_rate is not None else None,
            'interest_calculation_method': lead.interest_calculation_method, 'tenure_months': lead.loan_tenure_months,
            'monthly_repayment_amount': str(lead.monthly_repayment_amount) if lead.monthly_repayment_amount is not None else None,
            'total_scheduled_interest': str(totals['total_interest']) if totals['total_interest'] is not None else None,
            'total_scheduled_repayment': str(totals['total_repayment']) if totals['total_repayment'] is not None else None,
            'next_payment_due_date': next_schedule.due_date if next_schedule else lead.next_payment_due_date,
            'total_paid': str(verified_paid), 'remaining_balance': str(remaining)},
            'completed_payments': [row for row in history if row['status'] == 'VERIFIED'], 'upcoming_payments': upcoming, 'overdue_payments': overdue,
            'payment_history': history, 'upcoming_followups': [x for x in followups if x['status'] == 'PENDING'], 'completed_followups': [x for x in followups if x['status'] == 'COMPLETED']})

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        lead = self.get_object()
        new = request.data.get('status')
        allowed = {Lead.Status.NEW: {Lead.Status.CONTACTED}, Lead.Status.CONTACTED: {Lead.Status.APPROVED}, Lead.Status.APPROVED: {Lead.Status.DISBURSED}, Lead.Status.DISBURSED: {Lead.Status.COMPLETED}}
        if get_user_role_context(request.user, request)['hierarchy_level'] < 30:
            return Response({'detail': 'A staff account is required for lead status changes.'}, status=403)
        note = str(request.data.get('notes', '') or '').strip()
        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=lead.pk, organization=lead.organization)
            old = lead.status
            if new not in allowed.get(old, set()):
                return Response({'detail': f'Cannot move from {old} to {new}.'}, status=400)
            if new == Lead.Status.APPROVED:
                raw = request.data.get('approved_amount')
                try: approved = Decimal(str(raw))
                except (InvalidOperation, TypeError): return Response({'approved_amount': 'Enter a valid approved loan amount.'}, status=400)
                if approved <= 0 or (lead.requested_amount and approved > lead.requested_amount): return Response({'approved_amount': 'Amount must be positive and cannot exceed the requested amount.'}, status=400)
                try: rate = Decimal(str(request.data.get('annual_interest_rate')))
                except (InvalidOperation, TypeError): return Response({'annual_interest_rate': 'Enter a valid annual interest rate.'}, status=400)
                tenure_raw = request.data.get('loan_tenure_months')
                try: tenure = int(tenure_raw)
                except (TypeError, ValueError): return Response({'loan_tenure_months': 'Enter the approved tenure in months.'}, status=400)
                method = request.data.get('interest_calculation_method')
                methods = {'monthly_reducing', 'actual_365', 'actual_360', 'flat'}
                if rate < 0 or rate > 100 or not 1 <= tenure <= 600 or method not in methods:
                    return Response({'detail': 'Enter valid interest terms and a tenure from 1 to 600 months.'}, status=400)
                lead.approved_amount, lead.annual_interest_rate, lead.loan_tenure_months, lead.interest_calculation_method = approved, rate, tenure, method
            elif new == Lead.Status.DISBURSED:
                if lead.approved_amount is None or lead.annual_interest_rate is None or not lead.loan_tenure_months:
                    return Response({'detail': 'Approve the loan and record its terms before disbursement.'}, status=400)
                try: principal = Decimal(str(request.data.get('disbursed_amount')))
                except (InvalidOperation, TypeError): return Response({'disbursed_amount': 'Enter a valid disbursed principal.'}, status=400)
                try: deductions = Decimal(str(request.data.get('upfront_deductions_amount') or 0))
                except (InvalidOperation, TypeError): return Response({'upfront_deductions_amount': 'Enter a valid deduction amount.'}, status=400)
                if principal <= 0 or principal > lead.approved_amount or deductions < 0 or deductions >= principal:
                    return Response({'detail': 'Disbursed principal must be positive and no greater than approved; deductions must be lower than principal.'}, status=400)
                username = str(request.data.get('portal_login', '')).strip()
                password = str(request.data.get('portal_password', ''))
                User = get_user_model()
                if not username: return Response({'portal_login': 'A portal username is required at disbursement.'}, status=400)
                if User.objects.filter(username__iexact=username).exists(): return Response({'portal_login': 'This username is already in use.'}, status=400)
                try: validate_password(password)
                except ValidationError as error: return Response({'portal_password': list(error.messages)}, status=400)
                lead.disbursed_amount = principal
                lead.upfront_deductions_amount = deductions
                lead.net_disbursed_amount = principal - deductions
                lead.disbursed_at = timezone.now()
                lead.portal_user = User.objects.create_user(username=username, email=lead.email, password=password, first_name=lead.contact_name, default_organization=lead.organization)
            elif new == Lead.Status.COMPLETED and not lead.repayment_schedules.filter(organization=lead.organization).exists():
                return Response({'detail': 'Generate the repayment schedule before completing this lead.'}, status=400)
            lead.status = new
            if new == Lead.Status.COMPLETED:
                lead.completed_at = timezone.now()
            lead.save()
            LeadStatusHistory.objects.create(lead=lead, old_status=old, new_status=new, changed_by=request.user, notes=note)
        return Response({'detail': f'Lead moved to {new}.', 'lead': LeadSerializer(lead, context={'request': request}).data})

    @action(detail=True, methods=['get'], url_path='status-history')
    def status_history(self, request, pk=None):
        lead = self.get_object()
        rows = lead.status_history.select_related('changed_by').order_by('-changed_at')
        return Response(LeadStatusHistorySerializer(rows, many=True).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        rows = LeadAssignmentHistory.objects.filter(lead=self.get_object()).select_related('old_owner__user', 'new_owner__user', 'assigned_by').order_by('-assigned_at')
        return Response(LeadAssignmentHistorySerializer(rows, many=True).data)
