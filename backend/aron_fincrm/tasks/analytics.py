from decimal import Decimal
from django.db.models import Count, Q, Sum
from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from calendar import monthrange
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from applications.models import FinancialApplication
from customers.models import Customer
from finance.models import RepaymentPayment, RepaymentSchedule
from leads.models import Lead
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant
from tasks.models import ApplicationFollowUp, CustomerFollowUp, LeadFollowUp, Task
from organizations.date_filters import apply_date_range
from organizations.dates import organization_local_date


def scoped_work(request):
    org = get_user_organization(request.user, request)
    ctx = get_user_role_context(request.user, request)
    level = ctx['hierarchy_level']
    leads = Lead.objects.filter(organization=org)
    customers = Customer.objects.filter(organization=org)
    applications = FinancialApplication.objects.filter(organization=org)
    tasks = Task.objects.filter(organization=org)
    if not org or level < 30:
        return org, leads.none(), customers.none(), applications.none(), tasks.none()
    if level >= 90:
        return org, leads, customers, applications, tasks
    if level >= 70:
        manager = request.user.manager_set.first()
        departments = manager.managed_departments.all() if manager else []
        return (org,
                leads.filter(Q(assigned_to__department__in=departments) | Q(created_by__department__in=departments)).distinct(),
                customers.filter(assigned_to__department__in=departments),
                applications.filter(assigned_employee__department__in=departments),
                tasks.filter(Q(assigned_to__department__in=departments) | Q(department__in=departments) | Q(assigned_to_user=request.user)).distinct())
    if level >= 50:
        profile = request.user.teamlead_profiles.first()
        teams = profile.teams.all() if profile else []
        return (org,
                leads.filter(Q(assigned_to__team__in=teams) | Q(created_by__team__in=teams)).distinct(),
                customers.filter(assigned_to__team__in=teams),
                applications.filter(assigned_employee__team__in=teams),
                tasks.filter(Q(assigned_to__team__in=teams) | Q(team__in=teams) | Q(assigned_to_user=request.user)).distinct())
    employee = getattr(request.user, 'employee', None)
    return (org,
            leads.filter(assigned_to=employee),
            customers.filter(assigned_to=employee),
            applications.filter(assigned_employee=employee),
            tasks.filter(assigned_to=employee))


@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def pipeline(request):
    if get_user_role_context(request.user, request)['hierarchy_level'] < 30:
        return Response({'detail': 'A staff account is required to view the sales pipeline.'}, status=403)
    org, leads, _, applications, _ = scoped_work(request)
    if not org:
        return Response({'detail': 'Organization not found.'}, status=400)
    scoped_leads = leads
    leads = apply_date_range(leads, request, 'created_at')
    today = organization_local_date(request)
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    scoped_payments = RepaymentPayment.objects.filter(
        organization=org,
        repayment_schedule__lead__in=scoped_leads,
        verification_status='VERIFIED',
    )
    paid_this_month = scoped_payments.filter(
        payment_date__gte=month_start, payment_date__lte=month_end,
    ).aggregate(total=Sum('amount'))['total'] or 0
    if request.query_params.get('start_date') or request.query_params.get('end_date'):
        month_start = parse_date(request.query_params.get('start_date') or '') or today
        month_end = parse_date(request.query_params.get('end_date') or '') or today
    else:
        month_start = today.replace(day=1)
        month_end = today.replace(day=monthrange(today.year, today.month)[1])
    payment_totals = RepaymentPayment.objects.filter(
        repayment_schedule_id=OuterRef('pk'),
        verification_status='VERIFIED',
    ).order_by().values('repayment_schedule_id').annotate(total=Sum('amount')).values('total')
    amount_field = DecimalField(max_digits=15, decimal_places=2)
    schedules = RepaymentSchedule.objects.filter(
        organization=org,
        lead__in=scoped_leads,
    ).annotate(
        verified_amount=Coalesce(
            Subquery(payment_totals, output_field=amount_field),
            Value(Decimal('0.00')),
            output_field=amount_field,
        ),
    ).annotate(
        outstanding=ExpressionWrapper(
            F('expected_amount') - F('verified_amount'),
            output_field=amount_field,
        ),
    )
    overdue_lead_ids = set(schedules.filter(
        due_date__lt=today,
        status__in=['PENDING', 'PARTIAL'],
        outstanding__gt=0,
    ).values_list('lead_id', flat=True).distinct())
    due_lead_ids = set(schedules.filter(
        due_date__gte=month_start,
        due_date__lte=month_end,
    ).values_list('lead_id', flat=True).distinct())
    payments = apply_date_range(RepaymentPayment.objects.filter(organization=org, repayment_schedule__lead__in=scoped_leads), request, 'payment_date')
    in_range = payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
    paid_lead_ids = set(payments.filter(
        verification_status='VERIFIED',
    ).values_list('repayment_schedule__lead_id', flat=True).distinct())
    application_counts = dict(
        applications.filter(lead__in=scoped_leads)
        .values_list('lead_id')
        .annotate(count=Count('id'))
    )
    rows = []
    for lead in leads.select_related('assigned_to__user').order_by('-created_at'):
        payment_status = 'overdue' if lead.pk in overdue_lead_ids else 'paid' if lead.pk in paid_lead_ids else 'not_paid'
        rows.append({
            'id': str(lead.id), 'lead_code': lead.lead_code, 'contact_name': lead.contact_name,
            'status': lead.status, 'expected_amount': lead.expected_amount, 'currency': lead.currency,
            'assigned_to': lead.assigned_to.user.get_full_name() or lead.assigned_to.user.username if lead.assigned_to_id else '',
            'payment_status': payment_status, 'due_this_month': lead.pk in due_lead_ids,
            'application_count': application_counts.get(lead.pk, 0),
        })
    return Response({
        'total_leads': len(rows),
        'total_value': leads.aggregate(total=Sum('expected_amount'))['total'] or 0,
        'payments_this_month': paid_this_month,
        'payments_in_range': in_range,
        'paid': sum(row['payment_status'] == 'paid' for row in rows),
        'not_paid': sum(row['payment_status'] == 'not_paid' for row in rows),
        'overdue': sum(row['payment_status'] == 'overdue' for row in rows),
        'leads': rows,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def report_summary(request):
    if get_user_role_context(request.user, request)['hierarchy_level'] < 30:
        return Response({'detail': 'A staff account is required to view reports.'}, status=403)
    org, leads, customers, applications, tasks = scoped_work(request)
    if not org:
        return Response({'detail': 'Organization not found.'}, status=400)
    scoped_leads, scoped_customers, scoped_applications = leads, customers, applications
    leads = apply_date_range(leads, request, 'created_at')
    customers = apply_date_range(customers, request, 'created_at')
    applications = apply_date_range(applications, request, 'created_at')
    tasks = apply_date_range(tasks, request, 'created_at')
    followups = apply_date_range(CustomerFollowUp.objects.filter(organization=org, customer__in=scoped_customers), request, 'scheduled_at').count()
    followups += apply_date_range(LeadFollowUp.objects.filter(organization=org, lead__in=scoped_leads), request, 'scheduled_at').count()
    followups += apply_date_range(ApplicationFollowUp.objects.filter(organization=org, application__in=scoped_applications), request, 'scheduled_at').count()
    all_verified = RepaymentPayment.objects.filter(
        organization=org,
        repayment_schedule__lead__in=scoped_leads,
        verification_status='VERIFIED',
    )
    verified = apply_date_range(all_verified, request, 'payment_date')
    today = organization_local_date(request)
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    monthly_verified = all_verified.filter(payment_date__gte=month_start, payment_date__lte=month_end)
    qualified_leads = leads.filter(status=Lead.Status.QUALIFIED)
    return Response({
        'leads_by_status': list(leads.values('status').annotate(count=Count('id')).order_by('status')),
        'applications_by_status': list(applications.values('status').annotate(count=Count('id')).order_by('status')),
        'tasks_by_status': list(tasks.values('status').annotate(count=Count('id')).order_by('status')),
        'active_leads': leads.exclude(status__in=['unqualified']).count(),
        'won': qualified_leads.count(),
        'customers': customers.count(),
        'followups': followups,
        'tasks_overdue': tasks.filter(due_date__lt=timezone.now()).exclude(status__in=['COMPLETED', 'CANCELLED']).count(),
        'revenue_this_month': monthly_verified.aggregate(total=Sum('amount'))['total'] or 0,
        'revenue_in_range': verified.aggregate(total=Sum('amount'))['total'] or 0,
        'revenue_total': all_verified.aggregate(total=Sum('amount'))['total'] or 0,
    })
