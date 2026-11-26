import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('subscriptions', '0001_initial'),
        ('organizations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplatformsettings',
            name='invoice_issuer_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='subscriptionplatformsettings',
            name='invoice_issuer_address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='subscriptionplatformsettings',
            name='invoice_issuer_gstin',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='subscriptionplatformsettings',
            name='invoice_sac_hsn_code',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='subscriptionplatformsettings',
            name='invoice_gst_rate_percent',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='invoice_customer_gstin',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.CreateModel(
            name='AIAssistantUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('model_name', models.CharField(blank=True, max_length=150)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('total_tokens', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_assistant_usage', to='organizations.organizations_organization')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_assistant_usage', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'subscriptions_aiassistantusage',
                'ordering': ['-created_at'],
            },
        ),
    ]
