from django.db import migrations


def remove_ai_chatbot_artifacts(apps, schema_editor):
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    # Chat data is scoped to these tables; drop only those tables and their
    # migration history. This is safe on databases where the app was never used.
    with connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS {quote("ai_assistant_aimessage")}')
        cursor.execute(f'DROP TABLE IF EXISTS {quote("ai_assistant_aiconversation")}')
        cursor.execute(
            f'DELETE FROM {quote("django_migrations")} WHERE {quote("app")} = %s',
            ['ai_assistant'],
        )

    Plan = apps.get_model('subscriptions', 'Plan')
    plans = Plan.objects.using(connection.alias).only('pk', 'features')
    for plan in plans.iterator():
        features = plan.features
        if isinstance(features, dict) and 'ai_assistant' in features:
            features.pop('ai_assistant')
            Plan.objects.using(connection.alias).filter(pk=plan.pk).update(features=features)


class Migration(migrations.Migration):
    dependencies = [
        ('subscriptions', '0004_remove_plan_max_applications_per_month_and_more'),
    ]

    operations = [
        migrations.RunPython(remove_ai_chatbot_artifacts),
    ]
