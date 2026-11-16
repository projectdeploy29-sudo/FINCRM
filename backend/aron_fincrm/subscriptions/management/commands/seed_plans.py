from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = "Seeds standard SaaS subscription plans (Starter, Growth, Enterprise)."

    def handle(self, *args, **options):
        plans_data = [
            {
                "name": "Starter Plan",
                "code": "starter",
                "description": "Essential CRM features for small loan and insurance agencies (up to 5 staff members).",
                "monthly_price": 0.00,
                "yearly_price": 0.00,
                "max_employees": 5,
                "max_applications_per_month": 50,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "standard_support": True,
                },
                "is_active": True,
            },
            {
                "name": "Growth Plan",
                "code": "growth",
                "description": "Empowers growing finance companies with advanced department and team pipelines.",
                "monthly_price": 4999.00,
                "yearly_price": 49990.00,
                "max_employees": 25,
                "max_applications_per_month": 500,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "document_verification": True,
                    "repayments": True,
                    "team_dashboards": True,
                },
                "is_active": True,
            },
            {
                "name": "Enterprise Plan",
                "code": "enterprise",
                "description": "Full platform capabilities with unlimited scale and custom roles.",
                "monthly_price": 14999.00,
                "yearly_price": 149990.00,
                "max_employees": 100,
                "max_applications_per_month": 5000,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "document_verification": True,
                    "repayments": True,
                    "custom_roles": True,
                    "audit_logs": True,
                    "priority_support": True,
                },
                "is_active": True,
            },
        ]

        created_count = 0
        for data in plans_data:
            _, created = Plan.objects.update_or_create(
                code=data["code"],
                defaults=data,
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(plans_data)} subscription plans ({created_count} newly created)."))
