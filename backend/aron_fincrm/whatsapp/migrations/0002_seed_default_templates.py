from django.db import migrations


DEFAULT_MESSAGES = [
    (
        'Friendly reminder',
        'Please reply to confirm that this time works for you.',
        10,
    ),
    (
        'Need to reschedule?',
        'Our team is ready to help. Reply here if you have questions or need to reschedule.',
        20,
    ),
    (
        'Thank you',
        'Thank you for your time. Please reply if you need any further assistance.',
        30,
    ),
]


def add_default_messages(apps, schema_editor):
    MessageTemplate = apps.get_model('whatsapp', 'WhatsAppMessageTemplate')
    for title, body, sort_order in DEFAULT_MESSAGES:
        MessageTemplate.objects.get_or_create(
            organization=None,
            title=title,
            defaults={'body': body, 'sort_order': sort_order, 'is_active': True},
        )


def remove_default_messages(apps, schema_editor):
    MessageTemplate = apps.get_model('whatsapp', 'WhatsAppMessageTemplate')
    MessageTemplate.objects.filter(organization=None, title__in=[row[0] for row in DEFAULT_MESSAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [('whatsapp', '0001_initial')]

    operations = [migrations.RunPython(add_default_messages, migrations.RunPython.noop)]
