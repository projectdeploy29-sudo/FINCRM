import re

from django.db.models import Count, Q, Sum
from django.contrib.contenttypes.models import ContentType

from accounts.models import Manager, TeamLead
from customers.models import Customer
from employes.models import Employee
from communications.models import MessageDraft
from finance.models import RepaymentPayment, RepaymentSchedule
from leads.models import Lead
from organizations.models import Department, Team
from permitions.models import Role
from organizations.dates import organization_local_date
from organizations.tenant import get_user_organization, get_user_role_context
from tasks.models import CustomerFollowUp, LeadFollowUp, Task
from whatsapp.models import WhatsAppMessage
from subscriptions.entitlements import active_subscription, resource_usage


MAX_RECORDS_PER_TYPE = 8
RECENT_RECORDS_PER_TYPE = 5
SEARCH_STOP_WORDS = {
    'about', 'after', 'also', 'and', 'any', 'are', 'assigned', 'before',
    'between', 'customer', 'customers', 'details', 'does', 'from', 'give',
    'have', 'help', 'how', 'into', 'lead', 'leads', 'loan', 'loans', 'many',
    'more', 'most', 'open', 'please', 'record', 'records', 'show', 'status',
    'tell', 'that', 'the', 'their', 'there', 'these', 'this', 'those', 'what',
    'when', 'which', 'with', 'work', 'would', 'your',
    'task', 'tasks', 'payment', 'payments', 'followup',
    'followups', 'follow-up', 'follow-ups', 'current', 'recent', 'overdue',
}


def _none_querysets():
    return {
        'managers': Manager.objects.none(),
        'employees': Employee.objects.none(),
        'team_leads': TeamLead.objects.none(),
        'departments': Department.objects.none(),
        'teams': Team.objects.none(),
        'roles': Role.objects.none(),
        'message_drafts': MessageDraft.objects.none(),
        'whatsapp_messages': WhatsAppMessage.objects.none(),
        'leads': Lead.objects.none(),
        'customers': Customer.objects.none(),
        'tasks': Task.objects.none(),
        'schedules': RepaymentSchedule.objects.none(),
        'payments': RepaymentPayment.objects.none(),
        'customer_followups': CustomerFollowUp.objects.none(),
        'lead_followups': LeadFollowUp.objects.none(),
    }


def _accessible_whatsapp_messages(queryset, data):
    """Limit message history to leads and follow-ups visible in this request."""
    from leads.models import Lead
    from tasks.models import CostomerFollowUp

    lead_ids = data['leads'].values_list('id', flat=True)
    customer_followup_ids = data['customer_followups'].values_list('id', flat=True)
    lead_followup_ids = data['lead_followups'].values_list('id', flat=True)
    return queryset.filter(
        Q(followup_kind='lead', content_type=ContentType.objects.get_for_model(Lead, for_concrete_model=False), object_id__in=lead_ids)
        | Q(followup_kind='customer', content_type=ContentType.objects.get_for_model(CostomerFollowUp, for_concrete_model=False), object_id__in=customer_followup_ids)
        | Q(followup_kind='lead', content_type=ContentType.objects.get_for_model(LeadFollowUp, for_concrete_model=False), object_id__in=lead_followup_ids)
    ).distinct()


def _scoped_querysets(user, request):
    organization = get_user_organization(user, request)
    role = get_user_role_context(user, request)
    if not organization or not organization.is_active:
        return organization, role, 'No active organization scope is available.', _none_querysets()

    data = {
        # Staff and organization lists start empty and are populated below only
        # for roles whose corresponding API endpoints expose those records.
        'managers': Manager.objects.none(),
        'employees': Employee.objects.none(),
        'team_leads': TeamLead.objects.none(),
        'departments': Department.objects.none(),
        'teams': Team.objects.none(),
        'roles': Role.objects.filter(Q(is_system_role=True) | Q(organization=organization)).order_by('-is_system_role', 'name'),
        'message_drafts': MessageDraft.objects.filter(organization=organization).select_related('customer', 'created_by'),
        'whatsapp_messages': WhatsAppMessage.objects.filter(organization=organization).select_related('sent_by').order_by('-created_at'),
        'leads': Lead.objects.filter(organization=organization),
        'customers': Customer.objects.filter(organization=organization, archived_at__isnull=True),
        'tasks': Task.objects.filter(organization=organization),
        'schedules': RepaymentSchedule.objects.filter(organization=organization),
        'payments': RepaymentPayment.objects.filter(organization=organization),
        'customer_followups': CustomerFollowUp.objects.filter(organization=organization),
        'lead_followups': LeadFollowUp.objects.filter(organization=organization),
    }

    level = role['hierarchy_level']
    role_code = role['role_code']

    # Lead portal accounts can only ask about the lead and records linked to it.
    if role_code == 'lead_portal':
        own_leads = data['leads'].filter(portal_user=user)
        own_lead_ids = own_leads.values_list('id', flat=True)
        data['leads'] = own_leads
        linked_customer_ids = own_leads.values_list('customer_id', flat=True)
        data['customers'] = data['customers'].filter(id__in=linked_customer_ids).distinct()
        data['tasks'] = data['tasks'].none()
        data['schedules'] = data['schedules'].filter(lead_id__in=own_lead_ids)
        data['payments'] = data['payments'].filter(repayment_schedule_id__in=data['schedules'].values_list('id', flat=True))
        # Follow-up records are internal workflow, even when linked to a portal lead.
        data['customer_followups'] = data['customer_followups'].none()
        data['lead_followups'] = data['lead_followups'].none()
        data['roles'] = Role.objects.none()
        data['message_drafts'] = MessageDraft.objects.none()
        data['whatsapp_messages'] = WhatsAppMessage.objects.none()
        return organization, role, 'Only the authenticated lead portal account and records directly linked to it.', data

    if level >= 90:
        data['managers'] = Manager.objects.filter(organization=organization).select_related('user').order_by('created_at')
        data['employees'] = Employee.objects.filter(organization=organization).select_related('user', 'department', 'team', 'role', 'manager__user').order_by('employee_code')
        data['team_leads'] = TeamLead.objects.filter(organization=organization).select_related('user', 'department', 'manager__user').prefetch_related('teams').order_by('code')
        data['departments'] = Department.objects.filter(organization=organization).select_related('manager__user').annotate(
            teams_count=Count('team', distinct=True), employees_count=Count('employee', distinct=True),
        ).order_by('name')
        data['teams'] = Team.objects.filter(organization=organization).select_related(
            'department', 'team_lead__user', 'team_leader__user',
        ).annotate(members_count=Count('employee', distinct=True)).order_by('name')
        data['whatsapp_messages'] = _accessible_whatsapp_messages(data['whatsapp_messages'], data)
        return organization, role, 'All records in the authenticated user’s active organization.', data

    if level >= 70:
        manager = Manager.objects.filter(user=user, organization=organization).first()
        if not manager:
            return organization, role, 'No matching manager profile; no CRM records are available.', _none_querysets()
        departments = Department.objects.filter(organization=organization, manager=manager)
        department_ids = departments.values_list('id', flat=True)
        data['managers'] = Manager.objects.filter(organization=organization, user=user).select_related('user')
        data['employees'] = Employee.objects.filter(organization=organization).filter(
            Q(department_id__in=department_ids) | Q(manager__user=user)
        ).select_related('user', 'department', 'team', 'role', 'manager__user').order_by('employee_code')
        data['team_leads'] = TeamLead.objects.filter(
            organization=organization, department_id__in=department_ids,
        ).select_related('user', 'department', 'manager__user').prefetch_related('teams').order_by('code')
        data['departments'] = departments.select_related('manager__user').annotate(
            teams_count=Count('team', distinct=True), employees_count=Count('employee', distinct=True),
        ).order_by('name')
        data['teams'] = Team.objects.filter(organization=organization, department_id__in=department_ids).select_related(
            'department', 'team_lead__user', 'team_leader__user',
        ).annotate(members_count=Count('employee', distinct=True)).order_by('name')
        data['message_drafts'] = data['message_drafts'].filter(
            Q(customer__assigned_to__department_id__in=department_ids)
            | Q(customer__created_by__department_id__in=department_ids)
            | Q(created_by=user)
        ).distinct()
        data['leads'] = data['leads'].filter(assigned_to__department_id__in=department_ids)
        data['customers'] = data['customers'].filter(
            Q(created_by__department_id__in=department_ids)
            | Q(assigned_to__department_id__in=department_ids)
        ).distinct()
        data['tasks'] = data['tasks'].filter(
            Q(department_id__in=department_ids)
            | Q(assigned_to__department_id__in=department_ids)
            | Q(assigned_to_user=user)
            | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(lead__assigned_to__department_id__in=department_ids)
        data['payments'] = data['payments'].filter(repayment_schedule__lead__assigned_to__department_id__in=department_ids)
        followup_owners = {
            'customer_followups': 'customer__assigned_to',
            'lead_followups': 'lead__assigned_to',
        }
        for key, owner_path in followup_owners.items():
            data[key] = data[key].filter(
                Q(assigned_to__department_id__in=department_ids)
                | Q(**{owner_path + '__department_id__in': department_ids})
            ).distinct()
        data['whatsapp_messages'] = _accessible_whatsapp_messages(data['whatsapp_messages'], data)
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
        data['team_leads'] = TeamLead.objects.filter(organization=organization, user=user).select_related('user', 'department').prefetch_related('teams')
        data['teams'] = teams.select_related('department', 'team_lead__user', 'team_leader__user').annotate(
            members_count=Count('employee', distinct=True),
        ).order_by('name')
        data['employees'] = Employee.objects.filter(organization=organization, team_id__in=team_ids).select_related(
            'user', 'department', 'team', 'role', 'manager__user',
        ).order_by('employee_code')
        data['departments'] = Department.objects.filter(
            organization=organization, id__in=teams.values_list('department_id', flat=True),
        ).select_related('manager__user').annotate(
            teams_count=Count('team', distinct=True), employees_count=Count('employee', distinct=True),
        ).order_by('name')
        data['message_drafts'] = data['message_drafts'].filter(
            Q(customer__assigned_to__team_id__in=team_ids)
            | Q(customer__created_by__team_id__in=team_ids)
            | Q(created_by=user)
        ).distinct()
        data['leads'] = data['leads'].filter(assigned_to__team_id__in=team_ids)
        data['customers'] = data['customers'].filter(
            Q(created_by__team_id__in=team_ids) | Q(assigned_to__team_id__in=team_ids)
        ).distinct()
        data['tasks'] = data['tasks'].filter(
            Q(team_id__in=team_ids) | Q(assigned_to__team_id__in=team_ids)
            | Q(assigned_to_user=user) | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(lead__assigned_to__team_id__in=team_ids)
        data['payments'] = data['payments'].filter(repayment_schedule__lead__assigned_to__team_id__in=team_ids)
        followup_owners = {
            'customer_followups': 'customer__assigned_to',
            'lead_followups': 'lead__assigned_to',
        }
        for key, owner_path in followup_owners.items():
            data[key] = data[key].filter(
                Q(assigned_to__team_id__in=team_ids)
                | Q(**{owner_path + '__team_id__in': team_ids})
            ).distinct()
        data['whatsapp_messages'] = _accessible_whatsapp_messages(data['whatsapp_messages'], data)
        scope_names = list(teams.values_list('name', flat=True))
        return organization, role, 'Team lead scope: led teams ' + (', '.join(scope_names) or '(none).'), data

    if level >= 30:
        employee = getattr(user, 'employee', None)
        if not employee or employee.organization_id != organization.id:
            return organization, role, 'No matching employee profile; no CRM records are available.', _none_querysets()
        data['employees'] = Employee.objects.filter(pk=employee.pk).select_related(
            'user', 'department', 'team', 'role', 'manager__user',
        )
        data['message_drafts'] = data['message_drafts'].filter(
            Q(customer__assigned_to=employee) | Q(created_by=user)
        ).distinct()
        data['leads'] = data['leads'].filter(assigned_to=employee)
        data['customers'] = data['customers'].filter(assigned_to=employee)
        data['tasks'] = data['tasks'].filter(
            Q(assigned_to=employee) | Q(assigned_to_user=user) | Q(assigned_by_user=user)
        ).distinct()
        data['schedules'] = data['schedules'].filter(lead__assigned_to=employee)
        data['payments'] = data['payments'].filter(
            Q(recorded_by=employee)
            | Q(repayment_schedule__lead__assigned_to=employee)
        ).distinct()
        for key in ('customer_followups', 'lead_followups'):
            data[key] = data[key].filter(assigned_to=employee)
        data['whatsapp_messages'] = _accessible_whatsapp_messages(data['whatsapp_messages'], data)
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


def _manager_record(manager):
    user = manager.user
    return {
        'name': user.get_full_name() or user.username,
        'staff_code': manager.code,
        'designation': manager.designation,
        'employment_status': manager.employment_status,
        'managed_departments': list(manager.managed_departments.order_by('name').values_list('name', flat=True)),
        'created_at': manager.created_at.date().isoformat(),
    }


def _employee_record(employee):
    user = employee.user
    return {
        'name': user.get_full_name() or user.username,
        'staff_code': employee.employee_code,
        'designation': employee.designation,
        'department': employee.department.name if employee.department else None,
        'team': employee.team.name if employee.team else None,
        'role': employee.role.name if employee.role else 'General Employee',
        'manager': _employee_name(employee.manager) if employee.manager_id else None,
        'employment_status': employee.employment_status,
        'join_date': employee.join_date.isoformat() if employee.join_date else None,
    }


def _team_lead_record(team_lead):
    user = team_lead.user
    return {
        'name': (user.get_full_name() or user.username) if user else team_lead.code,
        'staff_code': team_lead.code,
        'designation': team_lead.designation,
        'department': team_lead.department.name if team_lead.department else None,
        'manager': (team_lead.manager.user.get_full_name() or team_lead.manager.user.username)
        if team_lead.manager_id and team_lead.manager.user else None,
        'teams': list(team_lead.teams.order_by('name').values_list('name', flat=True)),
        'employment_status': team_lead.employment_status,
    }


def _department_record(department):
    manager_user = department.manager.user if department.manager_id else None
    return {
        'name': department.name,
        'manager': (manager_user.get_full_name() or manager_user.username) if manager_user else None,
        'teams_count': getattr(department, 'teams_count', None) if getattr(department, 'teams_count', None) is not None else department.team_set.count(),
        'employees_count': getattr(department, 'employees_count', None) if getattr(department, 'employees_count', None) is not None else department.employee_set.count(),
        'is_active': department.is_active,
    }


def _team_record(team):
    team_lead_user = team.team_lead.user if team.team_lead_id else None
    employee_lead_user = team.team_leader.user if team.team_leader_id else None
    lead = team_lead_user or employee_lead_user
    return {
        'name': team.name,
        'department': team.department.name if team.department else None,
        'team_lead': (lead.get_full_name() or lead.username) if lead else None,
        'members_count': getattr(team, 'members_count', None) if getattr(team, 'members_count', None) is not None else team.employee_set.count(),
        'is_active': team.is_active,
    }


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
        'lead': item.lead.lead_code if item.lead else '',
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
        'lead': item.repayment_schedule.lead.lead_code if item.repayment_schedule and item.repayment_schedule.lead else '',
        'customer': item.repayment_schedule.customer.full_name or item.repayment_schedule.customer.legal_name if item.repayment_schedule and item.repayment_schedule.customer else '',
        'installment': item.repayment_schedule.installment_number if item.repayment_schedule else 0,
        'amount': str(item.amount),
        'payment_date': item.payment_date.isoformat(),
        'verification_status': item.verification_status,
    }


def _followup_record(item, kind):
    if kind == 'customer':
        reference = item.customer.customer_code
    else:
        reference = item.lead.lead_code
    return {
        'type': kind,
        'title': item.title or item.followup_type,
        'related_record': reference,
        'status': item.status,
        'scheduled_at': item.scheduled_at.isoformat(),
        'assigned_to': _employee_name(item.assigned_to),
    }


def _message_draft_record(item):
    return {
        'customer': item.customer.full_name or item.customer.legal_name,
        'channel': item.channel,
        'subject': item.subject,
        'message': item.message,
        'status': item.status,
        'created_by': item.created_by.get_full_name() or item.created_by.username,
        'created_at': item.created_at.isoformat(),
    }


def _whatsapp_message_record(item):
    # The API endpoint exposes message content to a user only after checking
    # access to the associated lead or follow-up. Match that exact scope here.
    return {
        'related_type': item.followup_kind,
        'recipient_name': item.recipient_name,
        'status': item.status,
        'sent_by': (item.sent_by.get_full_name() or item.sent_by.username) if item.sent_by else None,
        'created_at': item.created_at.isoformat(),
        'sent_at': item.sent_at.isoformat() if item.sent_at else None,
    }


def _subscription_summary(organization):
    """Return plan limits and usage for organization administrators only."""
    subscription = active_subscription(organization)
    if not subscription or not subscription.plan_id:
        return {
            'has_active_subscription': False,
            'message': 'No active or trial subscription was found for this organization.',
        }

    plan = subscription.plan
    staff_used = resource_usage(organization, 'employees')
    lead_used = resource_usage(organization, 'leads')
    staff_limit = plan.max_employees
    lead_limit = plan.max_leads
    return {
        'has_active_subscription': True,
        'plan': plan.name,
        'status': subscription.status,
        'billing_cycle': subscription.get_billing_cycle_display(),
        'start_date': subscription.start_date.date().isoformat(),
        'end_date': subscription.end_date.date().isoformat(),
        'next_billing_date': subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
        'staff_accounts': {
            'used': staff_used,
            'limit': staff_limit,
            'remaining': max(staff_limit - staff_used, 0) if staff_limit is not None else None,
        },
        'leads': {
            'used': lead_used,
            'limit': lead_limit,
            'remaining': max(lead_limit - lead_used, 0) if lead_limit is not None else None,
        },
        'features': plan.features if isinstance(plan.features, (dict, list)) else {},
        'included_services': plan.included_services if isinstance(plan.included_services, list) else [],
    }


def build_assistant_context(user, request, question):
    organization, role, scope_description, data = _scoped_querysets(user, request)
    if not organization:
        return None

    leads = data['leads'].select_related('assigned_to__user')
    customers = data['customers'].select_related('assigned_to__user')
    tasks = data['tasks'].select_related('assigned_to__user', 'assigned_to_user')
    schedules = data['schedules'].select_related('lead', 'customer')
    payments = data['payments'].select_related('repayment_schedule__lead', 'repayment_schedule__customer')

    followups = []
    terms = _search_terms(question)
    followup_sources = (
        ('customer', data['customer_followups'].select_related('customer', 'assigned_to__user'), ('title', 'followup_type', 'status', 'customer__customer_code', 'customer__full_name')),
        ('lead', data['lead_followups'].select_related('lead', 'assigned_to__user'), ('title', 'followup_type', 'status', 'lead__lead_code', 'lead__contact_name')),
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
        'managers': {
            'count': data['managers'].count(),
            'by_status': _status_counts(data['managers'], 'employment_status'),
        },
        'employees': {
            'count': data['employees'].count(),
            'by_status': _status_counts(data['employees'], 'employment_status'),
        },
        'team_leads': {
            'count': data['team_leads'].count(),
            'by_status': _status_counts(data['team_leads'], 'employment_status'),
        },
        'departments': {'count': data['departments'].count()},
        'teams': {'count': data['teams'].count()},
        'roles': {'count': data['roles'].count()},
        'message_drafts': {
            'count': data['message_drafts'].count(),
            'by_status': _status_counts(data['message_drafts'], 'status'),
            'by_channel': _status_counts(data['message_drafts'], 'channel'),
        },
        'whatsapp_messages': {
            'count': data['whatsapp_messages'].count(),
            'by_status': _status_counts(data['whatsapp_messages'], 'status'),
        },
        'leads': {
            'count': leads.count(),
            'by_status': _status_counts(leads, 'status'),
            'requested_amount_total': _sum(leads, 'requested_amount'),
            'approved_amount_total': _sum(leads, 'approved_amount'),
            'disbursed_amount_total': _sum(leads, 'disbursed_amount'),
        },
        'customers': {'count': customers.count(), 'by_status': _status_counts(customers, 'status')},
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
        'managers': _records(data['managers'], question,
            ('code', 'designation', 'user__username', 'user__first_name', 'user__last_name'),
            ('-created_at', ('user',)), _manager_record),
        'employees': _records(data['employees'], question,
            ('employee_code', 'designation', 'user__username', 'user__first_name', 'user__last_name', 'department__name', 'team__name'),
            ('employee_code', ('user', 'department', 'team', 'role', 'manager__user')), _employee_record),
        'team_leads': _records(data['team_leads'], question,
            ('code', 'designation', 'user__username', 'user__first_name', 'user__last_name', 'department__name'),
            ('code', ('user', 'department', 'manager__user')), _team_lead_record),
        'departments': _records(data['departments'], question,
            ('name', 'manager__user__username', 'manager__user__first_name', 'manager__user__last_name'),
            ('name', ('manager__user',)), _department_record),
        'teams': _records(data['teams'], question,
            ('name', 'department__name', 'team_lead__user__username', 'team_lead__user__first_name', 'team_lead__user__last_name'),
            ('name', ('department', 'team_lead__user', 'team_leader__user')), _team_record),
        'roles': _records(data['roles'], question, ('name', 'code', 'description'), ('name', ()),
            lambda item: {'name': item.name, 'code': item.code, 'description': item.description}),
        'message_drafts': _records(data['message_drafts'], question,
            ('subject', 'message', 'channel', 'status', 'customer__full_name', 'customer__legal_name'),
            ('-created_at', ('customer', 'created_by')), _message_draft_record),
        'whatsapp_messages': _records(data['whatsapp_messages'], question,
            ('recipient_name', 'status', 'followup_kind'),
            ('-created_at', ('sent_by',)), _whatsapp_message_record),
        'leads': _records(leads, question, ('lead_code', 'contact_name', 'status', 'priority'), ('-created_at', ('assigned_to__user',)), _lead_record),
        'customers': _records(customers, question, ('customer_code', 'full_name', 'legal_name', 'status', 'segment'), ('-created_at', ('assigned_to__user',)), _customer_record),
        'tasks': _records(tasks, question, ('title', 'status', 'priority'), ('-created_at', ('assigned_to__user', 'assigned_to_user')), _task_record),
        'repayment_schedules': _records(schedules, question, ('lead__lead_code', 'customer__full_name', 'status', 'payment_type'), ('due_date', ('lead', 'customer')), _schedule_record),
        'payments': _records(payments, question, ('repayment_schedule__lead__lead_code', 'repayment_schedule__customer__full_name', 'verification_status'), ('-payment_date', ('repayment_schedule__lead', 'repayment_schedule__customer')), _payment_record),
        'followups': [row[1] for row in followups[:MAX_RECORDS_PER_TYPE]],
    }

    if role['role_code'] == 'lead_portal':
        for record in records['leads']:
            record.pop('assigned_to', None)
        for record in records['customers']:
            record.pop('priority', None)
            record.pop('segment', None)
            record.pop('assigned_to', None)

    context = {
        'organization': organization.name,
        'role': role['role_name'],
        'authorized_scope': scope_description,
        'summaries': summary,
        'records': records,
    }
    # The organization profile endpoint is available to team leads and above.
    # Do not include its contact/location details for employee or lead accounts.
    if role['hierarchy_level'] >= 50 and role['role_code'] != 'lead_portal':
        context['organization_profile'] = {
            'name': organization.name,
            'legal_name': organization.legal_name,
            'city': organization.city,
            'state': organization.state,
            'country': organization.country,
            'timezone': organization.timezone,
            'currency': organization.currency,
        }
    context['current_user_access'] = {
        'role': role['role_name'],
        'permissions': role.get('permissions') or [],
    }
    # Subscription and seat-limit details are organization-level billing data.
    # Keep them out of the context supplied to managers, staff, and lead portals.
    if role['hierarchy_level'] >= 90 and role['role_code'] != 'lead_portal':
        context['subscription'] = _subscription_summary(organization)
    return context
