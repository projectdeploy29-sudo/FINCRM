from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.test import override_settings
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from unittest.mock import patch
from django.contrib.auth import get_user_model
from accounts.models import Manager, TeamLead
from employes.models import Employee
from organizations.models import Department, Organization, Team
from ai_assistant.data_access import build_assistant_context

from .assistant import is_ui_question, user_can_access
from .scanner import scan_frontend
from .sync import _enrich_feature_documentation


class UIQuestionRoutingTests(SimpleTestCase):
    def test_ui_questions_are_separated_from_record_queries(self):
        self.assertTrue(is_ui_question('Where is the Generate Repayment Schedule button?'))
        self.assertTrue(is_ui_question('How do I create a new customer?'))
        self.assertFalse(is_ui_question('How many managers do I have?'))
        self.assertFalse(is_ui_question('How many customers were added this month?'))

    def test_access_checks_use_role_context_and_feature_requirements(self):
        page = SimpleNamespace(minimum_role_level=30, allowed_role_codes=[], required_permissions=[])
        feature = SimpleNamespace(page=page, minimum_role_level=30, allowed_role_codes=[], required_permissions=[])
        self.assertTrue(user_can_access(feature, {'role_code': 'general_employee', 'hierarchy_level': 30, 'permissions': []}))
        self.assertFalse(user_can_access(feature, {'role_code': 'lead_portal', 'hierarchy_level': 20, 'permissions': []}))
        feature.required_permissions = ['finance.generate_schedule']
        self.assertFalse(user_can_access(feature, {'role_code': 'manager', 'hierarchy_level': 70, 'permissions': []}))
        self.assertTrue(user_can_access(feature, {'role_code': 'manager', 'hierarchy_level': 70, 'permissions': ['finance.generate_schedule']}))

    @override_settings(AI_ASSISTANT_API_URL='', AI_ASSISTANT_API_KEY='', AI_ASSISTANT_MODEL='')
    @patch('ai_assistant.views.get_user_organization', return_value=None)
    @patch('ai_assistant.views.public_feature_context', return_value={
        'feature': 'Generate repayment schedule', 'component_type': 'button',
        'purpose': 'Creates a schedule.', 'page': 'Repayment schedules',
        'navigation': 'Records → Payments → Repayment schedules',
        'location': 'Toolbar', 'workflow': ['Open the page.', 'Choose Generate repayment schedule.'],
        'source_evidence': {'condition': 'roleLevel >= 30'}, 'source_file': 'ResourcePage.jsx',
    })
    @patch('ai_assistant.views.user_can_access', return_value=True)
    @patch('ai_assistant.views.get_user_role_context', return_value={'role_code': 'employee', 'hierarchy_level': 30, 'permissions': []})
    @patch('ai_assistant.views.find_feature', return_value=SimpleNamespace(name='Generate repayment schedule'))
    @patch('ai_assistant.views.build_assistant_context')
    def test_ui_help_uses_source_catalog_without_database_question_context(self, build_context, *_mocks):
        from ai_assistant.views import AssistantChatView

        raw_request = APIRequestFactory().post('/api/v1/ai-assistant/chat/', {
            'question': 'Where is the Generate Repayment Schedule button?',
        }, format='json')
        request = AssistantChatView().initialize_request(raw_request)
        request.user = SimpleNamespace(is_authenticated=True)
        response = AssistantChatView().post(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['intent'], 'ui_help')
        self.assertIn('Records → Payments → Repayment schedules', response.data['answer'])
        build_context.assert_not_called()

    @override_settings(AI_ASSISTANT_API_URL='https://llm.example/v1/chat/completions', AI_ASSISTANT_API_KEY='test-key', AI_ASSISTANT_MODEL='test-model')
    @patch('ai_assistant.views.get_user_organization', return_value=None)
    @patch('ui_knowledge.assistant.find_feature', side_effect=AssertionError('CRM question must not search UI features'))
    @patch('ai_assistant.views.build_assistant_context', return_value={'authorized_scope': 'assigned organization', 'summaries': {'managers': {'count': 2}}})
    @patch('requests.post')
    def test_existing_crm_question_keeps_the_database_context_route(self, provider_post, build_context, *_mocks):
        from ai_assistant.views import AssistantChatView

        provider_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'choices': [{'message': {'content': 'There are 2 managers.'}}], 'usage': {}},
        )
        provider_post.return_value = provider_response
        raw_request = APIRequestFactory().post('/api/v1/ai-assistant/chat/', {
            'question': 'How many managers do I have?',
        }, format='json')
        request = AssistantChatView().initialize_request(raw_request)
        request.user = SimpleNamespace(is_authenticated=True)
        response = AssistantChatView().post(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['answer'], 'There are 2 managers.')
        build_context.assert_called_once()


class UISourceScannerTests(SimpleTestCase):
    def test_current_spa_exposes_repayment_schedule_action_with_source_evidence(self):
        project_root = Path(__file__).resolve().parents[3]
        snapshot = scan_frontend(project_root)
        feature = next(item for item in snapshot['features'] if item['name'] == 'Generate repayment schedule')
        self.assertEqual(feature['page_key'], 'schedules')
        self.assertEqual(feature['minimum_role_level'], 30)
        self.assertIn('first due date', ' '.join(feature['workflow']).lower())
        self.assertTrue(feature['evidence']['condition'])

    def test_scanner_discovers_all_frontend_modules_and_sidebar_items(self):
        project_root = Path(__file__).resolve().parents[3]
        snapshot = scan_frontend(project_root)
        page_ids = {page['module_id'] for page in snapshot['pages']}
        navigation_ids = {item['source_evidence']['module_id'] for item in snapshot['navigation']}
        self.assertIn('dashboard', page_ids)
        self.assertIn('billing', navigation_ids)
        self.assertIn('hierarchy', navigation_ids)
        self.assertNotIn('roles', page_ids)
        plans = next(page for page in snapshot['pages'] if page['module_id'] == 'plans')
        self.assertEqual(plans['minimum_role_level'], 90)
        schedule_tab = next(item for item in snapshot['navigation'] if item['key'] == 'nav-schedules')
        self.assertEqual(schedule_tab['source_evidence']['parent_module_id'], 'payments')

    @override_settings(AI_ASSISTANT_API_URL='https://llm.example/v1/chat/completions', AI_ASSISTANT_API_KEY='test-key', AI_ASSISTANT_MODEL='test-model')
    @patch('requests.post')
    def test_sync_enrichment_is_structured_and_source_grounded(self, provider_post):
        provider_post.return_value = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'choices': [{'message': {'content': '{"purpose":"Creates a schedule.","location":"Toolbar","workflow":["Open schedules.","Choose Generate."]}'}}]},
        )
        item = {'name': 'Generate repayment schedule', 'page_key': 'schedules', 'source_path': 'ResourcePage.jsx',
                'component_type': 'button', 'purpose': 'Source purpose.', 'location': 'Source location.',
                'workflow': ['Source workflow.'], 'evidence': {'condition': 'roleLevel >= 30'}}
        enriched, warning = _enrich_feature_documentation(item)
        self.assertTrue(enriched)
        self.assertFalse(warning)
        self.assertEqual(item['purpose'], 'Creates a schedule.')
        self.assertEqual(item['workflow'][-1], 'Choose Generate.')
        self.assertEqual(provider_post.call_args.kwargs['json']['temperature'], 0)

    @override_settings(AI_ASSISTANT_API_URL='', AI_ASSISTANT_API_KEY='', AI_ASSISTANT_MODEL='')
    def test_sync_enrichment_falls_back_without_provider_configuration(self):
        item = {'name': 'A feature', 'purpose': 'Known source purpose.', 'location': 'Toolbar', 'workflow': []}
        enriched, warning = _enrich_feature_documentation(item)
        self.assertFalse(enriched)
        self.assertIn('not configured', warning)
        self.assertEqual(item['purpose'], 'Known source purpose.')


class ManagerChatContextTests(TestCase):
    def test_org_admin_can_ask_for_manager_names_but_other_org_and_manager_records_stay_hidden(self):
        user_model = get_user_model()
        org = Organization.objects.create(name='Northstar', slug='northstar-chat')
        other_org = Organization.objects.create(name='Other', slug='other-chat')
        admin = user_model.objects.create_user('northstar_admin', password='test-password', default_organization=org)
        created_manager_user = user_model.objects.create_user(
            'aarav_manager', password='test-password', first_name='Aarav', last_name='Sharma',
        )
        another_manager_user = user_model.objects.create_user(
            'ananya_manager', password='test-password', first_name='Ananya', last_name='Patel',
        )
        outside_user = user_model.objects.create_user(
            'outside_manager', password='test-password', first_name='Outside', last_name='User',
        )
        Manager.objects.create(organization=org, user=created_manager_user, code='N-MGR-1', employment_status='active')
        Manager.objects.create(organization=org, user=another_manager_user, code='N-MGR-2', employment_status='active')
        Manager.objects.create(organization=other_org, user=outside_user, code='O-MGR-1', employment_status='active')
        manager = Manager.objects.get(user=created_manager_user)
        department = Department.objects.create(organization=org, manager=manager, name='Retail')
        team_lead_user = user_model.objects.create_user(
            'retail_lead', password='test-password', first_name='Riya', last_name='Kumar',
        )
        team_lead = TeamLead.objects.create(
            organization=org, user=team_lead_user, code='N-TL-1', department=department,
            manager=manager, employment_status='active',
        )
        team = Team.objects.create(organization=org, department=department, name='Retail East', team_lead=team_lead)
        employee_user = user_model.objects.create_user(
            'retail_employee', password='test-password', first_name='Sam', last_name='Rao',
        )
        Employee.objects.create(
            organization=org, user=employee_user, employee_code='N-E-1', department=department,
            team=team, employment_status='active',
        )

        admin_context = build_assistant_context(admin, None, 'What is the name of the manager I created?')
        names = [record['name'] for record in admin_context['records']['managers']]
        self.assertIn('Aarav Sharma', names)
        self.assertIn('Ananya Patel', names)
        self.assertNotIn('Outside User', names)
        self.assertEqual(admin_context['summaries']['managers']['count'], 2)
        self.assertEqual(admin_context['summaries']['employees']['count'], 1)
        self.assertEqual(admin_context['records']['employees'][0]['name'], 'Sam Rao')
        self.assertEqual(admin_context['records']['team_leads'][0]['name'], 'Riya Kumar')
        self.assertEqual(admin_context['records']['departments'][0]['name'], 'Retail')
        self.assertEqual(admin_context['records']['teams'][0]['name'], 'Retail East')

        manager_context = build_assistant_context(created_manager_user, None, 'What managers are in my organization?')
        self.assertEqual([item['name'] for item in manager_context['records']['managers']], ['Aarav Sharma'])
        self.assertEqual(manager_context['summaries']['managers']['count'], 1)
        self.assertEqual(manager_context['records']['employees'][0]['name'], 'Sam Rao')

        team_lead_context = build_assistant_context(team_lead_user, None, 'Who is on my team?')
        self.assertEqual([item['name'] for item in team_lead_context['records']['employees']], ['Sam Rao'])
        self.assertEqual([item['name'] for item in team_lead_context['records']['team_leads']], ['Riya Kumar'])
        self.assertEqual(team_lead_context['records']['managers'], [])

        employee_context = build_assistant_context(employee_user, None, 'Who is on my team?')
        self.assertEqual([item['name'] for item in employee_context['records']['employees']], ['Sam Rao'])
        self.assertEqual(employee_context['records']['managers'], [])
        self.assertEqual(employee_context['records']['team_leads'], [])
