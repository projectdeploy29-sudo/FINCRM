import re

from django.db.models import Count, Q, Sum

from accounts.models import Manager, TeamLead
from applications.models import FinancialApplication
from customers.models import Customer
from finance.models import RepaymentPayment, RepaymentSchedule
from leads.models import Lead
from organizations.models import Department, Team
from organizations.dates import organization_local_date
from organizations.tenant import get_user_organization, get_user_role_context
from tasks.models import ApplicationFollowUp, CustomerFollowUp, LeadFollowUp, Task


MAX_RECORDS_PER_TYPE = 8
RECENT_RECORDS_PER_TYPE = 5
SEARCH_STOP_WORDS = {
    'about', 'after', 'also', 'and', 'any', 'are', 'assigned', 'before',
    'between', 'customer', 'customers', 'details', 'does', 'from', 'give',
    'have', 'help', 'how', 'into', 'lead', 'leads', 'loan', 'loans', 'many',
    'more', 'most', 'open', 'please', 'record', 'records', 'show', 'status',
    'tell', 'that', 'the', 'their', 'there', 'these', 'this', 'those', 'what',
    'when', 'which', 'with', 'work', 'would', 'your', 'application',
    'applications', 'task', 'tasks', 'payment', 'payments', 'followup',
    'followups', 'follow-up', 'follow-ups', 'current', 'recent', 'overdue',
}


def _none_querysets():
    return {
        'leads': Lead.objects.none(),
        'customers': Customer.objects.none(),
        'applications': FinancialApplication.objects.none(),
        'tasks': Task.objects.none(),
        'schedules': RepaymentSchedule.objects.none(),
        'payments': RepaymentPayment.objects.none(),
        'customer_followups': CustomerFollowUp.objects.none(),
        'lead_followups': LeadFollowUp.objects.none(),
        'application_followups': ApplicationFollowUp.objects.none(),
    }


def _scoped_querysets(user, request):
    organization = get_user_organization(user, request)
    role = get_user_role_context(user, request)
    if not organization or not organization.is_active:
        return organization, role, 'No active organization scope is available.', _none_querysets()

    data = {
        'leads': Lead.objects.filter(organization=organization),
        'customers': Customer.objects.filter(organization=organization, archived_at__isnull=True),
        'applications': FinancialApplication.objects.filter(organization=organization),
        'tasks': Task.objects.filter(organization=organization),
        'schedules': RepaymentSchedule.objects.filter(organization=organization),
        'payments': RepaymentPayment.objects.filter(organization=organization),
        'customer_followups': CustomerFollowUp.objects.filter(organization=organization),
        'lead_followups': LeadFollowUp.objects.filter(organization=organization),
        'application_followups': ApplicationFollowUp.objects.filter(organization=organization),
    }

    level = role['hierarchy_level']
    role_code = role['role_code']

    # Lead portal accounts can only ask about the lead and records linked to it.
    if role_code == 'lead_portal':
        own_leads = data['leads'].filter(portal_user=user)
        own_lead_ids = own_leads.values_list('id', flat=True)
        own_application_ids = own_leads.exclude(application_id__isnull=True).values_list('application_id', flat=True)
        data['leads'] = own_leads
        data['applications'] = data['applications'].filter(
            Q(lead_id__in=own_lead_ids) | Q(id__in=own_application_ids)
        ).distinct()
        linked_customer_ids = own_leads.values_list('customer_id', flat=True)
        converted_customer_ids = own_leads.values_list('converted_customer_id', flat=True)
        data['customers'] = data['customers'].filter(
            Q(id__in=linked_customer_ids) | Q(id__in=converted_customer_ids)
            | Q(id__in=data['applications'].values_list('customer_id', flat=True))
        ).distinct()
        data['tasks'] = data['tasks'].none()
        data['schedules'] = data['schedules'].filter(application_id__in=data['applications'].values_list('id', flat=True))
        data['payments'] = data['payments'].filter(repayment_schedule_id__in=data['schedules'].values_list('id', flat=True))
        # Follow-up records are internal workflow, even when linked to a portal lead.
        data['customer_followups'] = data['customer_followups'].none()
        data['lead_followups'] = data['lead_followups'].none()
        data['application_followups'] = data['application_followups'].none()
        return organization, role, 'Only the authenticated lead portal account and records directly linked to it.', data

    if level >= 90:
        return organization, role, 'All records in the authenticated user’s active organization.', data

    if level >= 70:
        manager = Manager.objects.filter(user=user, organization=organization).first()
        if not manager:
            return organization, role, 'No matching manager profile; no CRM records are available.', _none_querysets()
        departments = Department.objects.filter(organization=organization, manager=manager)
        department_ids = departments.values_list('id', flat=True)
        data['leads'] = data['leads'].filter(assigned_to__department_id__in=department_ids)
        data['customers'] = data['customers'].filter(
            Q(created_by__department_id__in=department_ids)
            | Q(assigned_to__department_id__in=department_ids)
        ).distinct()
        data['applications'] = data['applications'].filter(assigned_employee__department_id__in=department_ids)
        data['tasks'] = data['tasks'].filter(
            Q(department_id__in=department_ids)
            | Q(assigned_to__department_id__in=department_ids)
            | Q(assigned_to_user=user)
            | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(application__assigned_employee__department_id__in=department_ids)
        data['payments'] = data['payments'].filter(repayment_schedule__application__assigned_employee__department_id__in=department_ids)
        followup_owners = {
            'customer_followups': 'customer__assigned_to',
            'lead_followups': 'lead__assigned_to',
            'application_followups': 'application__assigned_employee',
        }
        for key, owner_path in followup_owners.items():
            data[key] = data[key].filter(
                Q(assigned_to__department_id__in=department_ids)
                | Q(**{owner_path + '__department_id__in': department_ids})
            ).distinct()
        scope_names = list(departments.values_list('name', flat=True))
        return organization, role, 'Manager scope: managed departments ' + (', '.join(scope_names) or '(none).'), data

    if level >= 50:
        profile = TeamLead.objects.filter(user=user, organization=organization).first()
        teams = Team.objects.filter(organization=organization)
        team_filter = Q()
        if profile:
            team_filter |= Q(team_lead=profile)
        employee_profile = getattr(user, 'employee', None)
        if employee_profile and employee_profile.organization_id == organization.id:
            team_filter |= Q(team_leader=employee_profile)
        teams = teams.filter(team_filter) if team_filter else teams.none()
        if not profile and not (employee_profile and employee_profile.organization_id == organization.id):
            return organization, role, 'No matching team lead profile; no CRM records are available.', _none_querysets()
        team_ids = teams.values_list('id', flat=True)
        data['leads'] = data['leads'].filter(assigned_to__team_id__in=team_ids)
        data['customers'] = data['customers'].filter(
            Q(created_by__team_id__in=team_ids) | Q(assigned_to__team_id__in=team_ids)
        ).distinct()
        data['applications'] = data['applications'].filter(assigned_employee__team_id__in=team_ids)
        data['tasks'] = data['tasks'].filter(
            Q(team_id__in=team_ids) | Q(assigned_to__team_id__in=team_ids)
            | Q(assigned_to_user=user) | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(application__assigned_employee__team_id__in=team_ids)
        data['payments'] = data['payments'].filter(repayment_schedule__application__assigned_employee__team_id__in=team_ids)
        followup_owners = {
            'customer_followups': 'customer__assigned_to',
            'lead_followups': 'lead__assigned_to',
            'application_followups': 'application__assigned_employee',
        }
        for key, owner_path in followup_owners.items():
            data[key] = data[key].filter(
                Q(assigned_to__team_id__in=team_ids)
                | Q(**{owner_path + '__team_id__in': team_ids})
            ).distinct()
        scope_names = list(teams.values_list('name', flat=True))
        return organization, role, 'Team lead scope: led teams ' + (', '.join(scope_names) or '(none).'), data

    if level >= 30:
        employee = getattr(user, 'employee', None)
        if not employee or employee.organization_id != organization.id:
            return organization, role, 'No matching employee profile; no CRM records are available.', _none_querysets()
        data['leads'] = data['leads'].filter(assigned_to=employee)
        data['customers'] = data['customers'].filter(assigned_to=employee)
        data['applications'] = data['applications'].filter(assigned_employee=employee)
        data['tasks'] = data['tasks'].filter(
            Q(assigned_to=employee) | Q(assigned_to_user=user) | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(application__assigned_employee=employee)
        data['payments'] = data['payments'].filter(
            Q(recorded_by=employee)
            | Q(repayment_schedule__application__assigned_employee=employee)
        ).distinct()
        for key in ('customer_followups', 'lead_followups', 'application_followups'):
            data[key] = data[key].filter(assigned_to=employee)
        return organization, role, 'Employee scope: records assigned directly to the authenticated employee.', data

    return organization, role, 'This account has no CRM record scope.', _none_querysets()


def _status_counts(queryset, field):
    return {
        str(row[field] or 'unknown'): row['count']
        for row in queryset.values(field).annotate(count=Count('pk')).order_by(field)
    }


def _sum(queryset, field):
    value = queryset.aggregate(total=Sum(field))['total']
    return str(value) if value is not None else '0'


def _search_terms(question):
    words = re.findall(r'[\w-]{3,}', question.lower())
    return list(dict.fromkeys(word for word in words if word not in SEARCH_STOP_WORDS))[:4]


def _matching_queryset(queryset, fields, terms):
    if not terms:
        return queryset.none()
    filters = Q()
    for term in terms:
        term_filter = Q()
        for field in fields:
            term_filter |= Q(**{field + '__icontains': term})
        filters &= term_filter
    return queryset.filter(filters)


def _records(queryset, question, fields, ordering, serializer):
    terms = _search_terms(question)
    recent = list(queryset.select_related(*ordering[1]).order_by(ordering[0])[:RECENT_RECORDS_PER_TYPE])
    matching = list(
        _matching_queryset(queryset, fields, terms)
        .select_related(*ordering[1])
        .order_by(ordering[0])[:MAX_RECORDS_PER_TYPE]
    ) if terms else []
    records = []
    seen = set()
    for item in matching + recent:
        if item.pk in seen:
            continue
        seen.add(item.pk)
        records.append(serializer(item))
        if len(records) >= MAX_RECORDS_PER_TYPE:
            break
    return records


def _employee_name(employee):
    if not employee or not employee.user:
        return None
    return employee.user.get_full_name() or employee.user.username


def _lead_record(item):
    return {
        'code': item.lead_code,
        'name': item.contact_name,
        'status': item.status,
        'priority': item.priority,
        'source': item.source,
        'expected_amount': str(item.expected_amount) if item.expected_amount is not None else None,
        'currency': item.currency,
        'assigned_to': _employee_name(item.assigned_to),
        'created_at': item.created_at.date().isoformat(),
    }


def _customer_record(item):
    return {
        'code': item.customer_code,
        'name': item.full_name or item.legal_name,
        'status': item.status,
        'priority': item.priority,
        'segment': item.segment,
        'assigned_to': _employee_name(item.assigned_to),
        'created_at': item.created_at.date().isoformat(),
    }


def _application_record(item):
    return {
        'code': item.application_code,
        'type': item.application_type,
        'customer': item.customer.full_name or item.customer.legal_name,
        'status': item.status,
        'requested_amount': str(item.requested_amount) if item.requested_amount is not None else None,
        'approved_amount': str(item.approved_amount) if item.approved_amount is not None else None,
        'disbursed_amount': str(item.disbursed_amount) if item.disbursed_amount is not None else None,
        'net_disbursed_amount': str(item.net_disbursed_amount) if item.net_disbursed_amount is not None else None,
        'annual_interest_rate': str(item.annual_interest_rate) if item.annual_interest_rate is not None else None,
        'interest_calculation_method': item.interest_calculation_method,
        'loan_tenure_months': item.loan_tenure_months,
        'monthly_repayment_amount': str(item.monthly_repayment_amount) if item.monthly_repayment_amount is not None else None,
        'currency': item.currency,
        'next_payment_due_date': item.next_payment_due_date.isoformat() if item.next_payment_due_date else None,
        'assigned_to': _employee_name(item.assigned_employee),
        'created_at': item.created_at.date().isoformat(),
    }


def _task_record(item):
    assignee = _employee_name(item.assigned_to)
    if not assignee and item.assigned_to_user:
        assignee = item.assigned_to_user.get_full_name() or item.assigned_to_user.username
    return {
        'title': item.title,
        'status': item.status,
        'priority': item.priority,
        'due_date': item.due_date.date().isoformat() if item.due_date else None,
        'assigned_to': assignee,
    }


def _schedule_record(item):
    verified_received = item.payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
    outstanding = max(item.expected_amount - verified_received, 0)
    return {
        'application': item.application.application_code,
        'customer': item.customer.full_name or item.customer.legal_name,
        'installment': item.installment_number,
        'payment_type': item.payment_type,
        'expected_amount': str(item.expected_amount),
        'verified_received': str(verified_received),
        'outstanding_amount': str(outstanding),
        'due_date': item.due_date.isoformat(),
        'status': item.status,
    }


def _payment_record(item):
    return {
        'application': item.repayment_schedule.application.application_code,
        'customer': item.repayment_schedule.customer.full_name or item.repayment_schedule.customer.legal_name,
        'installment': item.repayment_schedule.installment_number,
        'amount': str(item.amount),
        'payment_date': item.payment_date.isoformat(),
        'verification_status': item.verification_status,
    }


def _followup_record(item, kind):
    if kind == 'customer':
        reference = item.customer.customer_code
    elif kind == 'lead':
        reference = item.lead.lead_code
    else:
        reference = item.application.application_code
    return {
        'type': kind,
        'title': item.title or item.followup_type,
        'related_record': reference,
        'status': item.status,
        'scheduled_at': item.scheduled_at.isoformat(),
        'assigned_to': _employee_name(item.assigned_to),
    }


def build_assistant_context(user, request, question):
    organization, role, scope_description, data = _scoped_querysets(user, request)
    if not organization:
        return None

    leads = data['leads'].select_related('assigned_to__user')
    customers = data['customers'].select_related('assigned_to__user')
    applications = data['applications'].select_related('customer', 'assigned_employee__user')
    tasks = data['tasks'].select_related('assigned_to__user', 'assigned_to_user')
    schedules = data['schedules'].select_related('application', 'customer')
    payments = data['payments'].select_related('repayment_schedule__application', 'repayment_schedule__customer')

    followups = []
    terms = _search_terms(question)
    followup_sources = (
        ('customer', data['customer_followups'].select_related('customer', 'assigned_to__user'), ('title', 'followup_type', 'status', 'customer__customer_code', 'customer__full_name')),
        ('lead', data['lead_followups'].select_related('lead', 'assigned_to__user'), ('title', 'followup_type', 'status', 'lead__lead_code', 'lead__contact_name')),
        ('application', data['application_followups'].select_related('application', 'assigned_to__user'), ('title', 'followup_type', 'status', 'application__application_code')),
    )
    for kind, queryset, search_fields in followup_sources:
        recent = list(queryset.order_by('-scheduled_at')[:RECENT_RECORDS_PER_TYPE])
        matching = list(
            _matching_queryset(queryset, search_fields, terms).order_by('-scheduled_at')[:MAX_RECORDS_PER_TYPE]
        ) if terms else []
        seen = set()
        for item in matching + recent:
            if item.pk in seen:
                continue
            seen.add(item.pk)
            followups.append((item.scheduled_at, _followup_record(item, kind)))
    followups.sort(key=lambda row: row[0], reverse=True)

    today = organization_local_date(request)
    overdue_schedules = schedules.filter(due_date__lt=today, status__in=('PENDING', 'PARTIAL'))
    summary = {
        'leads': {'count': leads.count(), 'by_status': _status_counts(leads, 'status')},
        'customers': {'count': customers.count(), 'by_status': _status_counts(customers, 'status')},
        'applications': {
            'count': applications.count(),
            'by_status': _status_counts(applications, 'status'),
            'requested_amount_total': _sum(applications, 'requested_amount'),
            'approved_amount_total': _sum(applications, 'approved_amount'),
            'disbursed_amount_total': _sum(applications, 'disbursed_amount'),
        },
        'tasks': {'count': tasks.count(), 'by_status': _status_counts(tasks, 'status')},
        'repayment_schedules': {
            'count': schedules.count(),
            'by_status': _status_counts(schedules, 'status'),
            'overdue_count': overdue_schedules.count(),
            'overdue_expected_amount': _sum(overdue_schedules, 'expected_amount'),
        },
        'payments': {
            'count': payments.count(),
            'by_verification_status': _status_counts(payments, 'verification_status'),
            'verified_amount_total': _sum(payments.filter(verification_status='VERIFIED'), 'amount'),
        },
        'followups': {
            'count': sum(queryset.count() for _, queryset, _ in followup_sources),
            'by_status': {
                kind: _status_counts(queryset, 'status')
                for kind, queryset, _ in followup_sources
            },
        },
    }

    records = {
        'leads': _records(leads, question, ('lead_code', 'contact_name', 'status', 'priority'), ('-created_at', ('assigned_to__user',)), _lead_record),
        'customers': _records(customers, question, ('customer_code', 'full_name', 'legal_name', 'status', 'segment'), ('-created_at', ('assigned_to__user',)), _customer_record),
        'applications': _records(applications, question, ('application_code', 'application_type', 'status'), ('-created_at', ('customer', 'assigned_employee__user')), _application_record),
        'tasks': _records(tasks, question, ('title', 'status', 'priority'), ('-created_at', ('assigned_to__user', 'assigned_to_user')), _task_record),
        'repayment_schedules': _records(schedules, question, ('application__application_code', 'customer__full_name', 'status', 'payment_type'), ('due_date', ('application', 'customer')), _schedule_record),
        'payments': _records(payments, question, ('repayment_schedule__application__application_code', 'repayment_schedule__customer__full_name', 'verification_status'), ('-payment_date', ('repayment_schedule__application', 'repayment_schedule__customer')), _payment_record),
        'followups': [row[1] for row in followups[:MAX_RECORDS_PER_TYPE]],
    }

    if role['role_code'] == 'lead_portal':
        for record in records['leads']:
            record.pop('assigned_to', None)
        for record in records['customers']:
            record.pop('priority', None)
            record.pop('segment', None)
            record.pop('assigned_to', None)
        for record in records['applications']:
            record.pop('assigned_to', None)

    return {
        'organization': organization.name,
        'role': role['role_name'],
        'authorized_scope': scope_description,
        'summaries': summary,
        'records': records,
    }
