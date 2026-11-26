from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ui_knowledge.models import UISyncRun
from ui_knowledge.sync import synchronize


class Command(BaseCommand):
    help = 'Scan the React source tree and synchronize pages, navigation, components, and UI features.'

    def add_arguments(self, parser):
        parser.add_argument('--frontend-root', help='Optional path to the React src directory or its project root.')
        parser.add_argument('--full', action='store_true', help='Record this run as an explicit full synchronization.')

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).resolve().parent.parent
        run = UISyncRun.objects.create(source_root=options.get('frontend_root') or str(project_root), full_sync=options['full'])
        self.stdout.write('UI Knowledge Synchronization Started')
        try:
            snapshot, counts = synchronize(project_root, options.get('frontend_root'), run=run)
        except Exception as exc:
            run.status = UISyncRun.Status.FAILED
            run.error = str(exc)
            run.completed_at = __import__('django.utils.timezone', fromlist=['now']).now()
            run.save(update_fields=['status', 'error', 'completed_at'])
            raise CommandError(f'UI knowledge synchronization failed; existing knowledge was preserved. {exc}') from exc

        for key in ('pages_discovered', 'pages_new', 'pages_updated', 'components_discovered',
                    'components_new', 'components_updated', 'features_discovered', 'features_new',
                    'features_updated', 'navigation_discovered', 'navigation_new',
                    'navigation_updated', 'deactivated'):
            self.stdout.write(f'{key.replace("_", " ").capitalize()}: {counts.get(key, 0)}')
        if run.warning:
            self.stdout.write(self.style.WARNING(run.warning))
        if run.status == UISyncRun.Status.PARTIAL:
            self.stdout.write(self.style.WARNING('Synchronization completed with documentation warnings; source-derived knowledge is available.'))
        else:
            self.stdout.write(self.style.SUCCESS('Synchronization completed successfully.'))
