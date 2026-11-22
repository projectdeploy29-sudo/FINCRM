from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_plan_catalog(apps, schema_editor):
    Plan = apps.get_model('subscriptions', 'Plan')
    database = schema_editor.connection.alias
    common_features = {
        'lead_management': True,
        'customer_management': True,
        'applications': True,
        'pipeline': True,
        'reports': True,
        'tasks': True,
        'followups': True,
    }
    plans = [
        {
            'name': 'Starter',
            'code': 'starter',
            'description': 'For small teams getting started with CRM.',
            'monthly_price': Decimal('1.00'),
            'yearly_price': Decimal('2.00'),
            'max_employees': 100,
            'max_leads': 500,
            'features': common_features,
        },
        {
            'name': 'Growth',
            'code': 'growth',
            'description': 'For growing teams that need more capacity.',
            'monthly_price': Decimal('2.00'),
            'yearly_price': Decimal('3.00'),
            'max_employees': 200,
            'max_leads': 1000,
            'features': {**common_features, 'advanced_reports': True},
        },
        {
            'name': 'Professional',
            'code': 'professional',
            'description': 'For professional teams that need maximum power.',
            'monthly_price': Decimal('3.00'),
            'yearly_price': Decimal('3.00'),
            'max_employees': 500,
            'max_leads': 5000,
            'features': {**common_features, 'advanced_reports': True, 'priority_support': True},
        },
        {
            'name': 'Enterprise',
            'code': 'enterprise',
            'description': 'Custom pricing and limits for enterprise organizations.',
            'monthly_price': None,
            'yearly_price': None,
            'max_employees': None,
            'max_leads': None,
            'features': {
                **common_features,
                'advanced_reports': True,
                'priority_support': True,
                'custom_roles': True,
                'dedicated_support': True,
            },
        },
    ]
    for plan in plans:
        Plan.objects.using(database).update_or_create(
            code=plan['code'],
            defaults={**plan, 'is_active': True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('organizations', '0002_team_team_lead_alter_team_team_leader'),
        ('subscriptions', '0005_remove_ai_chatbot_artifacts'),
    ]

    operations = [
        migrations.CreateModel(
            name='EnterpriseInquiry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('full_name', models.CharField(max_length=200)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(max_length=30)),
                ('organization_name', models.CharField(max_length=200)),
                ('website', models.URLField(blank=True)),
                ('linkedin_url', models.URLField(blank=True)),
                ('note', models.TextField(blank=True)),
                ('customer_email_sent', models.BooleanField(default=False)),
                ('admin_email_sent', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'subscriptions_enterpriseinquiry',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PlanCheckout',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('billing_cycle', models.CharField(choices=[('MONTHLY', 'Monthly'), ('YEARLY', 'Yearly')], max_length=10)),
                ('purchaser_email', models.EmailField(max_length=254)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('status', models.CharField(choices=[('creating', 'Creating Razorpay order'), ('pending', 'Awaiting payment'), ('processing', 'Payment verification in progress'), ('paid', 'Paid; registration pending'), ('activated', 'Subscription activated'), ('completed', 'Registration completed'), ('failed', 'Order creation failed')], default='creating', max_length=20)),
                ('razorpay_order_id', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('registration_token_hash', models.CharField(blank=True, max_length=64)),
                ('registration_token_expires_at', models.DateTimeField(blank=True, null=True)),
                ('registration_token_used_at', models.DateTimeField(blank=True, null=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('registration_email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='plan_checkouts', to='organizations.organizations_organization')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='checkouts', to='subscriptions.plan')),
            ],
            options={
                'db_table': 'subscriptions_plancheckout',
            },
        ),
        migrations.RunPython(seed_plan_catalog, migrations.RunPython.noop),
    ]
