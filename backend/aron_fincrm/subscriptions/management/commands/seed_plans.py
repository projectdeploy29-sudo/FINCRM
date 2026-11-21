from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = "Seeds subscription plans matching FINCRM pricing tiers."

    def handle(self, *args, **options):
        plans_data = [
            {
                "name": "Starter",
                "code": "starter",
                "description": "For small teams getting started with CRM.",
                "monthly_price": 2499.00,
                "yearly_price": None,
                "max_employees": 100,
                "max_leads": 500,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "pipeline": True,
                    "reports": True,
                    "tasks": True,
                    "followups": True,
                },
                "is_active": True,
            },
            {
                "name": "Growth",
                "code": "growth",
                "description": "For growing teams that need more capacity.",
                "monthly_price": 4999.00,
                "yearly_price": None,
                "max_employees": 200,
                "max_leads": 1000,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "pipeline": True,
                    "reports": True,
                    "tasks": True,
                    "followups": True,
                    "advanced_reports": True,
                },
                "is_active": True,
            },
            {
                "name": "Professional",
                "code": "professional",
                "description": "For professional teams that need maximum power.",
                "monthly_price": 9999.00,
                "yearly_price": None,
                "max_employees": 500,
                "max_leads": 5000,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "pipeline": True,
                    "reports": True,
                    "tasks": True,
                    "followups": True,
                    "advanced_reports": True,
                    "priority_support": True,
                },
                "is_active": True,
            },
            {
                "name": "Enterprise",
                "code": "enterprise",
                "description": "Custom recurring contract with negotiated limits.",
                "monthly_price": None,
                "yearly_price": None,
                "max_employees": None,
                "max_leads": None,
                "features": {
                    "lead_management": True,
                    "customer_management": True,
                    "applications": True,
                    "pipeline": True,
                    "reports": True,
                    "tasks": True,
                    "followups": True,
                    "advanced_reports": True,
                    "priority_support": True,
                    "custom_roles": True,
                    "dedicated_support": True,
                },
                "is_active": True,
            },
        ]

        for data in plans_data:
            Plan.objects.update_or_create(
                code=data["code"],
                defaults=data,
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(plans_data)} subscription plans."))
