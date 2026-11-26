import re
from urllib.parse import quote

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateformat import format as format_date
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from organizations.dates import organization_timezone
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant
from leads.models import Lead
from tasks.models import CostomerFollowUp, LeadFollowUp
from tasks.views import scope_followups

from .models import WhatsAppMessage, WhatsAppMessageTemplate
from .serializers import PrepareFollowupWhatsAppSerializer, PrepareLeadWhatsAppSerializer, WhatsAppMessageHistorySerializer, WhatsAppMessageTemplateSerializer


FOLLOWUP_MODELS = {
    'customer': (CostomerFollowUp, 'customer'),
    'lead': (LeadFollowUp, 'lead'),
}


def _accessible_followup(request, kind, followup_id):
    model, relation = FOLLOWUP_MODELS[kind]
    organization = get_user_organization(request.user, request)
    queryset = model.objects.filter(organization=organization)
    queryset = scope_followups(queryset, model, request.user, request)
    followup = get_object_or_404(queryset.select_related(relation), pk=followup_id)
    return followup, relation


def _accessible_lead(request, lead_id):
    user = request.user
    organization = get_user_organization(user, request)
    queryset = Lead.objects.filter(organization=organization) if organization else Lead.objects.none()
    role = get_user_role_context(user, request)
    level = role['hierarchy_level']
    if level < 90:
        if role['role_code'] == 'lead_portal':
            queryset = queryset.filter(portal_user=user)
        elif level >= 70:
            manager = user.manager_set.first() if hasattr(user, 'manager_set') else None
            departments = manager.managed_departments.all() if manager else []
            queryset = queryset.filter(assigned_to__department__in=departments)
        elif level >= 50:
            profiles = getattr(user, 'teamlead_profiles', None)
            if profiles and profiles.exists():
                teams = profiles.first().teams.values_list('id', flat=True)
                queryset = queryset.filter(assigned_to__team_id__in=teams)
            else:
                queryset = queryset.none()
        else:
            employee = getattr(user, 'employee', None)
            queryset = queryset.filter(assigned_to=employee) if employee else queryset.filter(created_by__user=user)
    return get_object_or_404(queryset, pk=lead_id)


def _contact_for_followup(followup, relation, kind, organization_country):
    related = getattr(followup, relation)
    if kind == 'customer':
        customer = related
        name = customer.full_name or customer.legal_name or 'Customer'
        phone = customer.primary_phone
        country = customer.country or organization_country
    else:
        name = related.contact_name or 'Lead'
        phone = related.phone
        country = organization_country
    return name, phone, country


def _international_phone(raw_phone, country=''):
    value = (raw_phone or '').strip()
    if value.startswith('00'):
        value = f'+{value[2:]}'
    digits = re.sub(r'\D', '', value)
    if not value.startswith('+'):
        normalized_country = re.sub(r'[^a-z]', '', (country or '').lower())
        is_india = normalized_country in {'india', 'in', 'bharat'}
        if is_india and len(digits) == 10:
            digits = f'91{digits}'
        elif is_india and len(digits) == 11 and digits.startswith('0'):
            digits = f'91{digits[1:]}'
        elif is_india and len(digits) == 12 and digits.startswith('91'):
            pass
        else:
            raise ValueError(
                'Add the country calling code to this phone number. For Indian 10-digit numbers, '
                'Auron FIN CRM adds +91 automatically when the contact or organization country is India.'
            )
    if not 8 <= len(digits) <= 15:
        raise ValueError('Recipient phone must be a valid international number with 8 to 15 digits.')
    return digits


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAuthenticatedTenant])
def templates(request):
    role = get_user_role_context(request.user, request)
    if role['hierarchy_level'] < 30:
        return Response({'detail': 'Only organization staff can use WhatsApp follow-ups.'}, status=status.HTTP_403_FORBIDDEN)
    organization = get_user_organization(request.user, request)
    queryset = WhatsAppMessageTemplate.objects.filter(is_active=True).filter(
        Q(organization__isnull=True) | Q(organization=organization)
    ).order_by('sort_order', 'title', 'id')
    return Response({
        'messages': WhatsAppMessageTemplateSerializer(queryset, many=True).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAuthenticatedTenant])
def followup_history(request):
    role = get_user_role_context(request.user, request)
    if role['hierarchy_level'] < 30:
        return Response({'detail': 'Only organization staff can use WhatsApp follow-ups.'}, status=status.HTTP_403_FORBIDDEN)
    kind = request.query_params.get('followup_kind')
    followup_id = request.query_params.get('followup_id')
    if kind not in FOLLOWUP_MODELS or not followup_id:
        return Response({'detail': 'Provide a valid followup_kind and followup_id.'}, status=status.HTTP_400_BAD_REQUEST)
    followup, _ = _accessible_followup(request, kind, followup_id)
    content_type = ContentType.objects.get_for_model(followup, for_concrete_model=False)
    messages = WhatsAppMessage.objects.filter(
        organization=get_user_organization(request.user, request),
        content_type=content_type,
        object_id=str(followup.pk),
    ).select_related('sent_by', 'source_template')[:20]
    return Response(WhatsAppMessageHistorySerializer(messages, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAuthenticatedTenant])
def prepare_followup(request):
    role = get_user_role_context(request.user, request)
    if role['hierarchy_level'] < 30:
        return Response({'detail': 'Only organization staff can use WhatsApp follow-ups.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = PrepareFollowupWhatsAppSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    followup, relation = _accessible_followup(request, data['followup_kind'], data['followup_id'])
    organization = get_user_organization(request.user, request)
    organization_country = getattr(organization, 'country', 'India')
    recipient_name, raw_phone, recipient_country = _contact_for_followup(
        followup, relation, data['followup_kind'], organization_country
    )
    try:
        recipient_phone = _international_phone(raw_phone, recipient_country)
    except ValueError as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

    template = None
    if data.get('template_id') is not None:
        template = get_object_or_404(
            WhatsAppMessageTemplate.objects.filter(is_active=True).filter(
                Q(organization__isnull=True) | Q(organization=organization)
            ),
            pk=data['template_id'],
        )
        message_copy = template.body.strip()
    else:
        message_copy = data['custom_message']

    followup_type = followup.get_followup_type_display()
    local_time = followup.scheduled_at.astimezone(organization_timezone(request))
    time_label = format_date(local_time, 'l, j F Y, g:i A')
    reason = followup.purpose.strip() or followup.description.strip() or 'Not specified'
    body = (
        f'Hello {recipient_name},\n\n'
        f'Follow-up details:\n'
        f'Type: {followup_type}\n'
        f'Time: {time_label}\n'
        f'Reason: {reason}\n\n'
        f'{message_copy}'
    )
    if len(body) > 4096:
        return Response({'detail': 'The follow-up details and selected message exceed WhatsApp’s 4096-character text limit.'}, status=status.HTTP_400_BAD_REQUEST)

    content_type = ContentType.objects.get_for_model(followup, for_concrete_model=False)
    message = WhatsAppMessage.objects.create(
        organization=organization,
        followup_kind=data['followup_kind'],
        content_type=content_type,
        object_id=str(followup.pk),
        recipient_name=recipient_name,
        recipient_phone=f'+{recipient_phone}',
        message_body=body,
        source_template=template,
        sent_by=request.user,
        status=WhatsAppMessage.Status.PREPARED,
    )
    whatsapp_url = f'https://wa.me/{recipient_phone}?text={quote(body, safe="")}'
    return Response({
        'detail': 'Message prepared. Review it in WhatsApp and press Send there.',
        'whatsapp_url': whatsapp_url,
        'message': WhatsAppMessageHistorySerializer(message).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAuthenticatedTenant])
def lead_history(request):
    role = get_user_role_context(request.user, request)
    if role['hierarchy_level'] < 30:
        return Response({'detail': 'Only organization staff can use WhatsApp messages.'}, status=status.HTTP_403_FORBIDDEN)
    lead_id = request.query_params.get('lead_id')
    if not lead_id:
        return Response({'detail': 'Provide a valid lead_id.'}, status=status.HTTP_400_BAD_REQUEST)
    lead = _accessible_lead(request, lead_id)
    content_type = ContentType.objects.get_for_model(lead, for_concrete_model=False)
    messages = WhatsAppMessage.objects.filter(
        organization=get_user_organization(request.user, request),
        content_type=content_type,
        object_id=str(lead.pk),
    ).select_related('sent_by', 'source_template')[:20]
    return Response(WhatsAppMessageHistorySerializer(messages, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAuthenticatedTenant])
def prepare_lead(request):
    role = get_user_role_context(request.user, request)
    if role['hierarchy_level'] < 30:
        return Response({'detail': 'Only organization staff can use WhatsApp messages.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = PrepareLeadWhatsAppSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    lead = _accessible_lead(request, data['lead_id'])
    organization = get_user_organization(request.user, request)
    recipient_name = lead.contact_name or 'Lead'
    try:
        recipient_phone = _international_phone(lead.phone, (getattr(organization, 'country', '') or 'India'))
    except ValueError as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

    template = None
    if data.get('template_id') is not None:
        template = get_object_or_404(
            WhatsAppMessageTemplate.objects.filter(is_active=True).filter(
                Q(organization__isnull=True) | Q(organization=organization)
            ),
            pk=data['template_id'],
        )
        message_copy = template.body.strip()
    else:
        message_copy = data['custom_message']
    body = f'Hello {recipient_name},\n\n{message_copy}'
    if len(body) > 4096:
        return Response({'detail': 'The selected message exceeds WhatsApp’s 4096-character text limit.'}, status=status.HTTP_400_BAD_REQUEST)

    content_type = ContentType.objects.get_for_model(lead, for_concrete_model=False)
    message = WhatsAppMessage.objects.create(
        organization=organization,
        followup_kind=WhatsAppMessage.FollowupKind.LEAD,
        content_type=content_type,
        object_id=str(lead.pk),
        recipient_name=recipient_name,
        recipient_phone=f'+{recipient_phone}',
        message_body=body,
        source_template=template,
        sent_by=request.user,
        status=WhatsAppMessage.Status.PREPARED,
    )
    whatsapp_url = f'https://wa.me/{recipient_phone}?text={quote(body, safe="")}'
    return Response({
        'detail': 'Message prepared. Review it in WhatsApp and press Send there.',
        'whatsapp_url': whatsapp_url,
        'message': WhatsAppMessageHistorySerializer(message).data,
    }, status=status.HTTP_201_CREATED)
