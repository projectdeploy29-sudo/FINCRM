from django.db import models
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from organizations.dates import organization_day_bounds


def apply_date_range(queryset, request, field='created_at'):
    """Apply inclusive start_date/end_date query parameters to a queryset."""
    start_value = request.query_params.get('start_date')
    end_value = request.query_params.get('end_date')
    if not start_value and not end_value:
        return queryset

    start = parse_date(start_value) if start_value else None
    end = parse_date(end_value) if end_value else None
    if start_value and not start:
        raise ValidationError({'start_date': 'Use YYYY-MM-DD.'})
    if end_value and not end:
        raise ValidationError({'end_date': 'Use YYYY-MM-DD.'})
    if start and end and start > end:
        raise ValidationError({'end_date': 'End date must be on or after start date.'})

    model_field = None
    current_model = queryset.model
    try:
        for part in field.split('__'):
            model_field = current_model._meta.get_field(part)
            if part != field.split('__')[-1]:
                current_model = model_field.related_model
    except Exception:
        model_field = None
    filters = {}
    if isinstance(model_field, models.DateTimeField):
        if start:
            filters[f'{field}__gte'] = organization_day_bounds(start, request)[0]
        if end:
            filters[f'{field}__lt'] = organization_day_bounds(end, request)[1]
    else:
        if start:
            filters[f'{field}__gte'] = start
        if end:
            filters[f'{field}__lte'] = end
    return queryset.filter(**filters)
