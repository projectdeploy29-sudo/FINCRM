"""Conservative static scanner for the current React SPA structure.

The scanner reads source files only. It does not execute frontend code or infer browser
URLs: this application navigates by module IDs, which are stored as module targets.
"""
import hashlib
import re
from pathlib import Path


def sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _balanced_block(source, start):
    """Return a balanced JS object/array beginning at start, respecting quoted strings."""
    opening = source[start]
    closing = {'{': '}', '[': ']'}[opening]
    depth, quote, escaped = 0, None, False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ('"', "'", '`'):
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return ''


def _objects(array_text):
    result = []
    index = 0
    while index < len(array_text):
        if array_text[index] == '{':
            block = _balanced_block(array_text, index)
            if not block:
                break
            result.append(block)
            index += len(block)
        else:
            index += 1
    return result


def _literal(block, key):
    match = re.search(rf"\b{re.escape(key)}\s*:\s*(['\"])(.*?)\1", block, re.S)
    return match.group(2).strip() if match else ''


def _number(block, key, default=0):
    match = re.search(rf"\b{re.escape(key)}\s*:\s*(\d+)", block)
    return int(match.group(1)) if match else default


def _normalize_label(value):
    return re.sub(r'\s+', ' ', value).strip().lower()


def _module_blocks(modules_source):
    match = re.search(r'export\s+const\s+modules\s*=\s*\[', modules_source)
    if not match:
        raise ValueError('Could not find the exported modules array in config/modules.js')
    array = _balanced_block(modules_source, modules_source.index('[', match.start()))
    if not array:
        raise ValueError('The modules array is incomplete')
    return _objects(array)


def _js_string(value):
    return value.replace('\\', '\\\\').replace("'", "\\'")


def _field_declarations(block):
    fields = []
    patterns = (
        (r"\btext\(\s*'([^']+)'\s*,\s*'([^']+)'", 'text'),
        (r"\boptions\(\s*'([^']+)'\s*,\s*\[[^\]]*\]\s*,\s*'([^']+)'", 'select'),
        (r"\bselect\(\s*'([^']+)'\s*,\s*'[^']+'\s*,\s*\{\s*label\s*:\s*'([^']+)'", 'select'),
        (r"\bselect\(\s*'([^']+)'\s*,\s*'[^']+'", 'select'),
        (r"\bmany\(\s*'([^']+)'\s*,\s*'[^']+'", 'multi-select'),
    )
    seen = set()
    for pattern, field_type in patterns:
        for match in re.finditer(pattern, block):
            name, label = match.group(1), match.group(2) if len(match.groups()) > 1 else match.group(1)
            if name in seen:
                continue
            seen.add(name)
            nearby = block[match.start():min(len(block), match.end() + 220)]
            fields.append({'name': name, 'label': label.strip(), 'type': field_type,
                           'required': bool(re.search(r'\brequired\s*:\s*true', nearby))})
    return fields


def _features_for_module(module_id, label, block, page_key, source_path, source_hash):
    features = []

    def add(name, kind, evidence, purpose='', workflow=None, level=None):
        normalized = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'feature'
        features.append({
            'page_key': page_key,
            'key': f'{page_key}-{normalized}'[:200],
            'name': name,
            'component_type': kind,
            'purpose': purpose,
            'location': f'{label} page',
            'workflow': workflow or [f'Open {label} from the sidebar.'],
            'evidence': evidence,
            'minimum_role_level': _number(block, 'minLevel', 0) if level is None else level,
            'allowed_role_codes': [],
            'required_permissions': [],
            'source_hash': source_hash,
            'source_path': source_path,
        })

    # Module label and declared description are direct source documentation.
    description = _literal(block, 'description')
    add(label, 'page', {'module_id': module_id, 'label': label, 'description': description,
                        'form_fields': _field_declarations(block)}, description,
        [f'Open {label} from the sidebar.'])

    if not re.search(r'\b(?:readOnly|creationDisabled)\s*:\s*true', block):
        create_roles = {
            'customers': (30, ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']),
            'leads': (30, ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']),
            'payments': (30, ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']),
            'tasks': (30, ['manager', 'team_lead', 'general_employee']),
            'customer-followups': (30, ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']),
            'lead-followups': (30, ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']),
            'employees': (50, ['manager', 'team_lead', 'org_admin', 'super_admin']),
            'teams': (70, ['manager', 'org_admin', 'super_admin']),
            'departments': (90, ['org_admin', 'super_admin']),
            'managers': (90, ['org_admin', 'super_admin']),
            'team-leads': (70, ['manager', 'org_admin', 'super_admin']),
        }
        if module_id in create_roles:
            level, roles = create_roles[module_id]
            add(f'Create {label.rstrip("s")}', 'button', {
                'source_rule': 'ResourcePage canCreate and canCreateByRole',
                'module_id': module_id,
                'fields': _field_declarations(block),
            }, f'Opens the create form for {label.lower()}.',
                [f'Open {label} from the sidebar.', f'Choose Create {label.rstrip("s")}.', 'Complete the form and submit.'],
                level=level)
            features[-1]['allowed_role_codes'] = roles

    if not re.search(r'\b(?:readOnly|editDisabled)\s*:\s*true', block):
        edit_level = _number(block, 'editLevel', 30 if module_id in {'customers', 'leads'} else 50)
        if module_id in {'customers', 'leads', 'employees', 'managers', 'team-leads'}:
            edit_roles = (
                ['org_admin', 'super_admin', 'manager', 'team_lead', 'general_employee']
                if module_id in {'customers', 'leads'} else
                ['org_admin', 'super_admin'] if edit_level >= 90 else
                ['org_admin', 'super_admin', 'manager']
            )
            add(f'Edit {label.rstrip("s")}', 'table_action', {
                'source_rule': 'ResourcePage canEditRow', 'module_id': module_id,
                'opens': 'RecordForm',
            }, f'Opens the selected {label.rstrip("s").lower()} record for editing.',
                [f'Open {label} from the sidebar.', 'Select the record.', 'Choose Edit, update its fields, and submit.'],
                level=edit_level)
            features[-1]['allowed_role_codes'] = edit_roles

    # Extract action labels and form fields declared with text/select/options helpers.
    for action_block in re.findall(r'\{\s*label\s*:\s*([\'\"])(.*?)\1[\s\S]*?(?=\},\s*\{|\]\s*\}|$)', block):
        action_name = action_block[1].strip()
        if action_name:
            add(action_name, 'table_action', {'declared_action': action_name},
                f'{action_name} is an action declared for {label}.', [f'Open {label}.', f'Select {action_name}.'])

    for label_literal in re.findall(r"\b(?:text|options|select)\(\s*'[^']+'\s*,\s*'([^']+)'", block):
        add(label_literal.strip(), 'form', {'field_label': label_literal.strip()},
            f'{label_literal.strip()} is a field in the {label} form.')

    if module_id == 'schedules':
        # This control is declared in ResourcePage.jsx rather than modules.js.
        pass
    return features


def discover_frontend(project_root, explicit_root=None):
    """Find the React source root by structure, not by a fixed project path."""
    root = Path(explicit_root).resolve() if explicit_root else Path(project_root).resolve()
    candidates = []
    for path in root.rglob('modules.js'):
        if not explicit_root and set(path.relative_to(root).parts) & {'.git', 'node_modules', 'venv', 'tmp', 'dist', 'build', '__pycache__'}:
            continue
        if path.name == 'modules.js' and path.parent.name == 'config' and (path.parent.parent / 'App.jsx').exists():
            candidates.append(path.parent.parent)
    if not candidates:
        for path in root.rglob('App.jsx'):
            if not explicit_root and set(path.relative_to(root).parts) & {'.git', 'node_modules', 'venv', 'tmp', 'dist', 'build', '__pycache__'}:
                continue
            if path.parent.name == 'src':
                candidates.append(path.parent)
    if len(candidates) != 1:
        raise ValueError(f'Expected one React src directory; found {len(candidates)}. Pass --frontend-root to select it.')
    return candidates[0]


def scan_frontend(project_root, explicit_root=None):
    src = discover_frontend(project_root, explicit_root)
    modules_path = src / 'config' / 'modules.js'
    shell_path = src / 'components' / 'AppShell.jsx'
    resource_path = src / 'components' / 'ResourcePage.jsx'
    app_path = src / 'App.jsx'
    required = [modules_path, shell_path, resource_path, app_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError('Required UI source file(s) missing: ' + ', '.join(missing))

    modules_text = modules_path.read_text(encoding='utf-8')
    shell_text = shell_path.read_text(encoding='utf-8')
    resource_text = resource_path.read_text(encoding='utf-8')
    app_text = app_path.read_text(encoding='utf-8')
    base_match = re.search(r'const\s+baseModules\s*=\s*\[([^\]]*)\]', app_text)
    base_modules = set(re.findall(r"['\"]([^'\"]+)['\"]", base_match.group(1))) if base_match else set()
    rel = lambda path: path.relative_to(Path(project_root).resolve()).as_posix()
    pages, features, components = [], [], []

    for block in _module_blocks(modules_text):
        module_id = _literal(block, 'id')
        label = _literal(block, 'label')
        if not module_id or not label:
            continue
        if module_id != 'enterprise-management' and module_id not in base_modules and module_id not in {
            'tasks', 'customer-followups', 'lead-followups', 'schedules',
        }:
            # A module declaration by itself does not make the page reachable;
            # App.jsx is the authority for pages that the current application renders.
            continue
        key = re.sub(r'[^a-z0-9]+', '-', module_id.lower()).strip('-')
        role_start = app_text.find('const visibleModules = useMemo')
        role_end = app_text.find('}), [roleLevel, roleCode])', role_start) if role_start >= 0 else -1
        module_visibility_source = app_text[role_start:role_end + 3] if role_start >= 0 and role_end >= 0 else ''
        minimum_level = _number(block, 'minLevel', 0)
        minimum_level = {
            'plans': 90, 'managers': 90, 'departments': 90, 'organization': 90,
            'team-leads': 70, 'teams': 70, 'employees': 50,
        }.get(module_id, minimum_level)
        page_hash = sha256(block + module_visibility_source + f'|effective-role-level:{minimum_level}')
        pages.append({
            'key': key, 'title': label, 'nav_label': label, 'module_id': module_id,
            'frontend_route': '', 'source_path': rel(modules_path),
            'minimum_role_level': minimum_level,
            'source_hash': page_hash,
            'allowed_role_codes': ['super_admin'] if module_id == 'enterprise-management' else [],
            'required_permissions': [],
        })
        features.extend(_features_for_module(module_id, label, block, key, rel(modules_path), page_hash))

    # Explicit navigation arrays in AppShell are the canonical sidebar hierarchy.
    for array_name, parent_label in (('navItems', ''), ('recordItems', 'Records')):
        match = re.search(rf'const\s+{array_name}\s*=\s*\[', shell_text)
        if not match:
            continue
        array = _balanced_block(shell_text, shell_text.index('[', match.start()))
        for module_id, label in re.findall(r"\['([^']+)'\s*,\s*'([^']+)'\]", array):
            components.append({
                'key': f'nav-{module_id}', 'name': label, 'component_type': 'navigation',
                'source_path': rel(shell_path), 'source_hash': sha256(f'{array_name}:{module_id}:{label}:{parent_label}'),
                'source_evidence': {'module_id': module_id, 'label': label, 'parent': parent_label},
            })
    components.append({
        'key': 'nav-records', 'name': 'Records', 'component_type': 'navigation_group',
        'source_path': rel(shell_path), 'source_hash': sha256('AppShell:Records:recordItems'),
        'source_evidence': {'module_id': '', 'label': 'Records', 'parent': ''},
    })
    # Payments contains an in-page tab switcher for schedules and payments;
    # repayment schedules are not a top-level sidebar item in this SPA.
    payments_page = re.search(r'function\s+PaymentsPage\s*\([^)]*\)\s*\{[\s\S]*?const\s+sections\s*=\s*\[', app_text)
    if payments_page:
        sections_start = app_text.index('[', app_text.index('const sections', payments_page.start()))
        sections_block = _balanced_block(app_text, sections_start)
        for module_id, label in re.findall(r"\['([^']+)'\s*,\s*'([^']+)'\]", sections_block):
            if module_id == 'payments':
                continue  # Payments is already the sidebar parent of this tab set.
            components.append({
                'key': f'nav-{module_id}', 'name': label, 'component_type': 'tab',
                'source_path': rel(app_path), 'source_hash': sha256(f'PaymentsPage:{module_id}:{label}'),
                'source_evidence': {'module_id': module_id, 'label': label, 'parent': 'Payments',
                                    'parent_module_id': 'payments', 'control': 'PaymentsPage tab'},
            })
    followups_page = re.search(r'function\s+FollowUpsPage\s*\([^)]*\)\s*\{([\s\S]*?)(?=function\s+PaymentsPage)', app_text)
    if followups_page:
        followups_block = followups_page.group(1)
        for module_id, label in re.findall(r"\['([^']+-followups)'\s*,\s*'([^']+)'\]", followups_block):
            components.append({
                'key': f'tab-{module_id}', 'name': label, 'component_type': 'tab',
                'source_path': rel(app_path), 'source_hash': sha256(f'FollowUpsPage:{module_id}:{label}'),
                'source_evidence': {'module_id': module_id, 'label': label, 'parent': 'Follow-ups',
                                    'parent_module_id': 'followups', 'control': 'FollowUpsPage tab'},
            })

    page_ids = {page['module_id'] for page in pages}
    custom_page_components = {
        'dashboard': 'Dashboard', 'pipeline': 'PipelinePage', 'reports': 'ReportPage',
        'followups': 'FollowUpsPage', 'today': 'TodayPage', 'settings': 'SettingsPage',
        'payments': 'PaymentsPage',
    }
    app_rel = rel(app_path)
    for nav_component in list(components):
        nav = nav_component['source_evidence']
        module_id = nav.get('module_id')
        if not module_id or module_id in page_ids:
            continue
        label = nav['label']
        page_key = re.sub(r'[^a-z0-9]+', '-', module_id.lower()).strip('-')
        component_name = custom_page_components.get(module_id)
        component_reference = f'<{component_name}' if component_name else module_id
        evidence = app_text[app_text.find(component_reference):app_text.find(component_reference) + 700] if component_name and component_reference in app_text else nav_component['source_hash']
        level = 30 if module_id == 'followups' else 0
        pages.append({
            'key': page_key, 'title': label, 'nav_label': label,
            'nav_parent': nav.get('parent', ''), 'frontend_route': '', 'module_id': module_id,
            'source_path': app_rel if component_name else nav_component['source_path'],
            'minimum_role_level': level, 'allowed_role_codes': [], 'required_permissions': [],
            'source_hash': sha256(str(evidence) + nav_component['source_hash']),
        })
        feature_key = f'{page_key}-page-overview'
        features.append({
            'page_key': page_key, 'key': feature_key, 'name': label,
            'component_type': 'page', 'purpose': f'{label} workspace in FinCRM.',
            'location': f'{nav.get("parent") + " → " if nav.get("parent") else ""}{label}',
            'workflow': [f'Open {label} from the sidebar.'],
            'evidence': {'module_id': module_id, 'navigation_label': label, 'rendering_evidence': str(evidence)},
            'minimum_role_level': level, 'allowed_role_codes': [], 'required_permissions': [],
            'source_hash': sha256(str(evidence) + nav_component['source_hash']), 'source_path': app_rel,
        })
        page_ids.add(module_id)

    # React component inventory and their source hashes; relationships are linked to
    # discovered pages by module references and filename/name references.
    for file_path in sorted(src.rglob('*')):
        if file_path.suffix not in ('.jsx', '.js', '.tsx', '.ts') or not file_path.is_file():
            continue
        source = file_path.read_text(encoding='utf-8', errors='replace')
        for name in re.findall(r'\bfunction\s+([A-Z][A-Za-z0-9_]*)\s*\(|\bconst\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:\([^)]*\)\s*=>|\w+\s*=>)', source):
            component_name = next((part for part in name if part), '')
            if not component_name:
                continue
            component_key = re.sub(r'[^a-z0-9]+', '-', component_name.lower()).strip('-')
            related = [page['key'] for page in pages if page['module_id'] in source]
            components.append({
                'key': f'component-{component_key}', 'name': component_name,
                'component_type': 'react_component', 'source_path': rel(file_path),
                'source_hash': sha256(source), 'source_evidence': {'component': component_name, 'file': rel(file_path), 'page_keys': related},
            })

    # Capture concrete text controls in page-specific JSX files. Repeated generic
    # controls (Edit/Close/Save/etc.) are represented once by page/action metadata
    # above, so the catalogue stays feature-based instead of instance-based.
    component_page = {name: key for key, name in custom_page_components.items()}
    page_by_key = {page['key']: page for page in pages}
    generic_labels = {'close', 'cancel', 'save', 'create', 'edit', 'refresh', 'search', 'back', 'done', 'customers', 'leads'}
    for file_path in sorted(src.rglob('*.jsx')):
        if file_path.name in {'ResourcePage.jsx', 'App.jsx', 'AppShell.jsx'}:
            continue
        source = file_path.read_text(encoding='utf-8', errors='replace')
        component_names = set(re.findall(r'\bfunction\s+([A-Z][A-Za-z0-9_]*)\s*\(', source))
        target_keys = {component_page[name] for name in component_names if name in component_page}
        if not target_keys:
            continue
        for button_match in re.finditer(r'<button\b([^>]*)>([\s\S]*?)</button\s*>', source, re.I):
            attributes, content = button_match.group(1), button_match.group(2)
            aria = re.search(r'\baria-label\s*=\s*[\'"]([^\'"]+)[\'"]', attributes, re.I)
            title = re.search(r'\btitle\s*=\s*[\'"]([^\'"]+)[\'"]', attributes, re.I)
            visible = re.sub(r'\{[^{}]*\}', ' ', content)
            visible = re.sub(r'<[^>]*>', ' ', visible)
            label = ' '.join((aria.group(1) if aria else title.group(1) if title else visible).split()).strip(' +↗→')
            if not label or len(label) > 120 or _normalize_label(label) in generic_labels:
                continue
            for page_key in target_keys:
                page = page_by_key.get(page_key)
                if not page:
                    continue
                feature_key = f"{page_key}-button-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}"[:200]
                evidence_source = button_match.group(0)
                features.append({
                    'page_key': page_key, 'key': feature_key, 'name': label,
                    'component_type': 'button', 'purpose': f'{label} control on the {page["title"]} page.',
                    'location': f'{page["title"]} page', 'workflow': [f'Open {page["title"]} from the sidebar.', f'Choose {label}.'],
                    'evidence': {'label': label, 'button_source': evidence_source,
                                 'aria_label': aria.group(1) if aria else '',
                                 'title': title.group(1) if title else ''},
                    'minimum_role_level': page['minimum_role_level'], 'allowed_role_codes': [],
                    'required_permissions': [], 'source_hash': sha256(evidence_source),
                    'source_path': rel(file_path),
                })

    # Add the UI-only control using its exact rendering condition from ResourcePage.
    generate_match = re.search(r"module\.id\s*===\s*'schedules'\s*&&\s*roleLevel\s*>=\s*(\d+)[\s\S]{0,350}?Generate repayment schedule", resource_text, re.I)
    schedules = next((p for p in pages if p['module_id'] == 'schedules'), None)
    if generate_match and schedules:
        evidence = {
            'condition': generate_match.group(0),
            'handler': "setActionForm({ title: 'Generate repayment schedule', endpoint: '/finance/schedules/generate/', fields: module.fieldsGenerate })",
            'fields': ['Disbursed lead', 'Installments', 'First due date', 'Payment type'],
        }
        generation_source = sha256(
            generate_match.group(0)
            + modules_text[modules_text.find("id: 'schedules'"):modules_text.find("id: 'payments'")]
            + (payments_page.group(0) if payments_page else '')
        )
        feature_key = f"{schedules['key']}-generate-repayment-schedule"[:200]
        features.append({
            'page_key': schedules['key'], 'key': feature_key, 'name': 'Generate repayment schedule',
            'component_type': 'button',
            'purpose': 'Creates a repayment schedule using a disbursed lead and schedule details.',
            'location': 'Repayment schedules page toolbar',
            'workflow': ['Open Records → Payments → Repayment schedules.', 'Choose Generate repayment schedule.',
                         'Enter the disbursed lead, installments, first due date, and payment type.', 'Choose Create.'],
            'evidence': evidence, 'minimum_role_level': int(generate_match.group(1)),
            'allowed_role_codes': [], 'required_permissions': [], 'source_hash': generation_source,
            'source_path': rel(resource_path),
        })
        components.append({
            'key': 'component-' + feature_key, 'name': 'Generate repayment schedule',
            'component_type': 'button', 'source_path': rel(resource_path), 'source_hash': generation_source,
            'source_evidence': evidence, 'page_keys': [schedules['key']],
        })

    # Keep deterministic ordering and remove repeated declarations.
    unique_features = {}
    for feature in features:
        unique_features[(feature['page_key'], feature['key'])] = feature
    unique_components = {item['key']: item for item in components}
    for feature in unique_features.values():
        feature['evidence']['role_visibility_source'] = 'App.jsx module minLevel and ResourcePage role checks'
        feature['evidence']['app_role_filter_hash'] = sha256(app_text)
        if feature['component_type'] == 'button' and feature['name'].startswith('Create '):
            create_match = re.search(r'const\s+canCreateByRole\s*=\s*\{', resource_text)
            staff_match = re.search(r'const\s+staffTypeByModule\s*=\s*\{', resource_text)
            role_rules = ''
            if create_match:
                role_rules += _balanced_block(resource_text, resource_text.index('{', create_match.start()))
            if staff_match:
                role_rules += resource_text[staff_match.start():resource_text.find('const employeeRole', staff_match.start())]
            create_rule = re.search(r'const\s+canCreate\s*=\s*[^\n]+', resource_text)
            if create_rule:
                role_rules += create_rule.group(0)
            feature['source_hash'] = sha256(feature['source_hash'] + role_rules)
            feature['evidence']['role_visibility_source'] = role_rules.strip()
        elif feature['evidence'].get('source_rule') == 'ResourcePage canEditRow':
            edit_rule = re.search(r'const\s+canEditRow\s*=\s*[^\n]+', resource_text)
            role_rules = edit_rule.group(0) if edit_rule else ''
            feature['source_hash'] = sha256(feature['source_hash'] + role_rules)
            feature['evidence']['role_visibility_source'] = role_rules
        component_key = 'component-' + feature['key']
        unique_components.setdefault(component_key, {
            'key': component_key, 'name': feature['name'], 'component_type': feature['component_type'],
            'source_path': feature['source_path'], 'source_hash': feature['source_hash'],
            'source_evidence': feature['evidence'], 'page_keys': [feature['page_key']],
        })
    return {
        'source_root': str(src), 'pages': pages,
        'features': list(unique_features.values()), 'components': list(unique_components.values()),
            'navigation': [item for item in unique_components.values() if item['component_type'] in ('navigation', 'tab', 'navigation_group')],
    }
