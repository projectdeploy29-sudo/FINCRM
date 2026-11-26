import re
from difflib import SequenceMatcher

from .models import UIFeature, UINavigationItem


UI_INTENT = re.compile(
    r'\b(where|which page|which screen|how do i|how can i|how to|find|locate|'
    r'button|menu|sidebar|tab|option|screen|page|navigate|open|access|create|edit|update|manage|generate|download)\b',
    re.I,
)
NON_UI_COUNT = re.compile(r'\b(how many|count|total|number of|how much|list|show me|who is)\b', re.I)


def is_ui_question(question):
    text = question.strip()
    if not UI_INTENT.search(text):
        return False
    # Preserve normal CRM questions such as “How many managers can I create?” as
    # UI intent only when there is an explicit UI location/control question.
    if NON_UI_COUNT.search(text) and not re.search(r'\b(where|which page|which screen|button|menu|sidebar|tab|option)\b', text, re.I):
        return False
    return True


def _normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def _score(question, feature):
    query = _normalize(question)
    names = [feature.name, feature.page.title]
    names += list(feature.evidence.get('aliases', [])) if isinstance(feature.evidence, dict) else []
    best = 0.0
    for name in names:
        normalized = _normalize(name)
        if normalized and normalized in query:
            best = max(best, 1.0 + len(normalized) / max(len(query), 1))
        else:
            query_words, name_words = set(query.split()), set(normalized.split())
            if name_words:
                best = max(best, len(query_words & name_words) / len(name_words))
            best = max(best, SequenceMatcher(None, query, normalized).ratio() * 0.82)
    aliases = {
        'generate repayment schedule': ('repayment schedule', 'repayment schedul', 'schedule button', 'emi schedule'),
        'create customers': ('new customer', 'add customer', 'create customer'),
        'create lead': ('new lead', 'add lead', 'create lead'),
    }
    for name, variants in aliases.items():
        if name == _normalize(feature.name) and any(variant in query for variant in variants):
            best = max(best, 1.15)
    action = None
    if re.search(r'\b(create|add|new|onboard)\b', query):
        action = 'create'
    elif re.search(r'\b(update|edit|change|modify)\b', query):
        action = 'edit'
    elif re.search(r'\b(generate|make|produce)\b', query):
        action = 'generate'
    elif re.search(r'\b(delete|remove)\b', query):
        action = 'delete'
    if action:
        feature_name = _normalize(feature.name)
        expected = {
            'create': ('create ', 'add ', 'new ', 'onboard '),
            'edit': ('edit ', 'update ', 'change ', 'modify '),
            'generate': ('generate ', 'create ', 'build '),
            'delete': ('delete ', 'remove '),
        }[action]
        name_words = set(feature_name.split())
        action_words = {'create', 'add', 'new', 'onboard', 'edit', 'update', 'change', 'modify', 'generate', 'make', 'produce', 'delete', 'remove', 'build'}
        specific_words = name_words - action_words
        has_subject_match = bool(specific_words & set(query.split()))
        if has_subject_match and feature_name.startswith(expected):
            best += 0.85
        elif feature.component_type == 'form' or feature.component_type == 'page':
            best -= 0.55
        elif has_subject_match:
            best -= 0.25
    return best


def find_feature(question):
    features = list(UIFeature.objects.filter(is_active=True, page__is_active=True).select_related('page', 'component'))
    ranked = sorted(((_score(question, feature), feature) for feature in features), key=lambda pair: pair[0], reverse=True)
    if not ranked or ranked[0][0] < 0.48:
        return None
    if len(ranked) > 1 and ranked[0][0] < 0.72 and ranked[0][0] - ranked[1][0] < 0.08:
        return None
    return ranked[0][1]


def navigation_path(page):
    items = list(UINavigationItem.objects.filter(is_active=True).select_related('parent'))
    by_module = {item.module_id: item for item in items if item.module_id}
    item = by_module.get(page.module_id)
    labels = [item.label] if item else [page.nav_label or page.title]
    parent = item.parent if item else None
    visited = set()
    while parent and parent.pk not in visited:
        visited.add(parent.pk)
        labels.insert(0, parent.label)
        parent = parent.parent
    return ' → '.join(labels)


def user_can_access(feature, role_context):
    if role_context.get('role_code') in {'anonymous', 'lead_portal'}:
        return False
    level = int(role_context.get('hierarchy_level') or 0)
    role_code = role_context.get('role_code') or ''
    page = feature.page
    if role_code == 'super_admin':
        return page.module_id in {'enterprise-management', 'edit-plans', 'settings'}
    if page.allowed_role_codes and role_code not in page.allowed_role_codes:
        return False
    if level < page.minimum_role_level or level < feature.minimum_role_level:
        return False
    if feature.allowed_role_codes:
        allowed = set(feature.allowed_role_codes)
        if role_code not in allowed:
            # The existing frontend maps employee roles without an explicit
            # create mapping to its general_employee capability set.
            employee_fallback = level == 30 and role_code not in {'manager', 'team_lead', 'org_admin'}
            if not (employee_fallback and 'general_employee' in allowed):
                return False
    granted = set(role_context.get('permissions') or [])
    required = set(feature.required_permissions or []) | set(page.required_permissions or [])
    return not required or '*' in granted or required.issubset(granted)


def public_feature_context(feature):
    return {
        'feature': feature.name,
        'component_type': feature.component_type,
        'purpose': feature.purpose,
        'page': feature.page.title,
        'navigation': navigation_path(feature.page),
        'location': feature.location,
        'workflow': feature.workflow,
        'source_evidence': feature.evidence,
        'source_file': feature.component.source_path,
    }
