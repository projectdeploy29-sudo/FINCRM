from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Manager, TeamLead
from customers.models import Customer
from employes.models import Employee
from finance.models import RepaymentPayment, RepaymentSchedule
from leads.models import Lead
from organizations.models import Department, Organization, Team
from permitions.models import Role
from subscriptions.models import Payment, Plan, Subscription
from tasks.models import (
    CostomerFollowUp,
    LeadFollowUp,
    Task,
)


class Command(BaseCommand):
    help = "Create or refresh an isolated FINCRM demo organization and sample records."

    def handle(self, *args, **options):
        User = get_user_model()
        today = timezone.localdate()
        now = timezone.now()
        password = "FinCRM-Demo-2026!"

        organization, _ = Organization.objects.update_or_create(
            slug="fincrm-demo",
            defaults={
                "name": "FINCRM Demo Workspace",
                "legal_name": "FINCRM Demo Workspace",
                "email": "admin@fincrm-demo.test",
                "phone": "+91 90000 00000",
                "city": "Pune",
                "state": "Maharashtra",
                "country": "India",
                "timezone": "Asia/Kolkata",
                "currency": "INR",
                "is_active": True,
            },
        )

        accounts = {}
        for username, first_name, last_name, email in (
            ("demo_admin", "Aarav", "Admin", "admin@fincrm-demo.test"),
            ("demo_manager", "Maya", "Manager", "maya@fincrm-demo.test"),
            ("demo_teamlead", "Rohan", "Teamlead", "rohan@fincrm-demo.test"),
            ("demo_employee", "Priya", "Employee", "priya@fincrm-demo.test"),
        ):
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                    "default_organization": organization,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            accounts[username] = user

        manager, _ = Manager.objects.update_or_create(
            user=accounts["demo_manager"],
            defaults={
                "organization": organization,
                "code": "DEMO-MGR-001",
                "work_email": accounts["demo_manager"].email,
                "designation": "Sales Manager",
                "employment_status": Manager.ManagerStatus.ACTIVE,
                "join_date": today - timedelta(days=365),
            },
        )
        department, _ = Department.objects.update_or_create(
            organization=organization,
            name="Sales",
            defaults={"description": "Demo sales department", "manager": manager},
        )
        teamlead, _ = TeamLead.objects.update_or_create(
            user=accounts["demo_teamlead"],
            defaults={
                "organization": organization,
                "code": "DEMO-TL-001",
                "department": department,
                "manager": manager,
                "work_email": accounts["demo_teamlead"].email,
                "designation": "Sales Team Lead",
                "employment_status": TeamLead.teamStatus.ACTIVE,
                "join_date": today - timedelta(days=180),
            },
        )
        team, _ = Team.objects.update_or_create(
            organization=organization,
            name="Pioneer Team",
            defaults={
                "department": department,
                "team_lead": teamlead,
                "description": "Demo team for role and assignment checks",
            },
        )
        employee_role = Role.objects.get(code="general_employee", organization__isnull=True)
        employee, _ = Employee.objects.update_or_create(
            user=accounts["demo_employee"],
            defaults={
                "organization": organization,
                "employee_code": "DEMO-EMP-001",
                "department": department,
                "team": team,
                "role": employee_role,
                "work_email": accounts["demo_employee"].email,
                "designation": "Sales Employee",
                "employment_status": Employee.EmploymentStatus.ACTIVE,
                "join_date": today - timedelta(days=90),
            },
        )

        customer, _ = Customer.objects.update_or_create(
            organization=organization,
            customer_code="DEMO-CUST-001",
            defaults={
                "customer_type": Customer.CustomerType.INDIVIDUAL,
                "full_name": "Ananya Sharma",
                "primary_phone": "+91 98765 40001",
                "email": "ananya@example.test",
                "preferred_channel": Customer.PreferredChannel.WHATSAPP,
                "city": "Pune",
                "state": "Maharashtra",
                "source": "Referral",
                "status": Customer.Status.CONVERTED,
                "requested_amount": "240000.00",
                "currency": "INR",
                "created_by": employee,
                "assigned_to": employee,
                "notes": "Demo customer record",
            },
        )
        lead, _ = Lead.objects.update_or_create(
            organization=organization,
            lead_code="DEMO-LEAD-001",
            defaults={
                "contact_name": "Ananya Sharma",
                "phone": customer.primary_phone,
                "email": customer.email,
                "city": customer.city,
                "state": customer.state,
                "assigned_to": employee,
                "customer": customer,
                "source": Lead.Source.REFERRAL,
                "priority": Lead.Priority.HIGH,
                "status": Lead.Status.DISBURSED,
                "expected_amount": "240000.00",
                "requested_amount": "240000.00",
                "approved_amount": "220000.00",
                "disbursed_amount": "220000.00",
                "upfront_deductions_amount": "0.00",
                "net_disbursed_amount": "220000.00",
                "annual_interest_rate": "12.0000",
                "interest_calculation_method": "monthly_reducing",
                "loan_tenure_months": 12,
                "monthly_repayment_amount": "19554.00",
                "disbursed_at": now - timedelta(days=10),
                "currency": "INR",
                "created_by": employee,
            },
        )
        task_specs = (
            ("DEMO-TASK-MANAGER", "Check team conversion progress", accounts["demo_manager"], accounts["demo_admin"], 1, Task.Priority.MEDIUM),
            ("DEMO-TASK-TEAMLEAD", "Review employee follow-ups", accounts["demo_teamlead"], accounts["demo_manager"], 0, Task.Priority.HIGH),
            ("DEMO-TASK-EMPLOYEE", "Call Ananya about the next installment", accounts["demo_employee"], accounts["demo_teamlead"], 0, Task.Priority.MEDIUM),
        )
        Task.objects.filter(
            organization=organization,
            description="Seeded demo task (DEMO-TASK-ADMIN)",
        ).delete()
        for code, title, assignee, assigner, due_in_days, priority in task_specs:
            Task.objects.update_or_create(
                organization=organization,
                title=title,
                defaults={
                    "description": f"Seeded demo task ({code})",
                    "assigned_by_user": assigner,
                    "assigned_to_user": assignee,
                    "department": department,
                    "team": team,
                    "related_customer": customer,
                    "related_lead": lead,
                    "priority": priority,
                    "status": Task.Status.PENDING,
                    "start_date": now,
                    "due_date": now + timedelta(days=due_in_days),
                },
            )

        CostomerFollowUp.objects.update_or_create(
            organization=organization,
            customer=customer,
            followup_type="CALL",
            defaults={
                "created_by": employee,
                "scheduled_at": now + timedelta(hours=2),
                "status": "PENDING",
                "notes": "Confirm repayment date",
            },
        )
        LeadFollowUp.objects.update_or_create(
            organization=organization,
            lead=lead,
            followup_type="MEETING",
            defaults={
                "created_by": employee,
                "scheduled_at": now + timedelta(days=1),
                "status": "PENDING",
                "notes": "Discuss additional requirements",
            },
        )
        schedule, _ = RepaymentSchedule.objects.update_or_create(
            lead=lead,
            installment_number=1,
            defaults={
                "organization": organization,
                "customer": customer,
                "lead": lead,
                "payment_type": RepaymentSchedule.PaymentType.EMI,
                "expected_amount": "12000.00",
                "due_date": today - timedelta(days=4),
                "status": RepaymentSchedule.Status.PARTIAL,
                "notes": "Demo installment with a partial verified payment",
            },
        )
        payment, _ = RepaymentPayment.objects.update_or_create(
            repayment_schedule=schedule,
            transaction_reference="DEMO-UPI-001",
            defaults={
                "organization": organization,
                "amount": "5000.00",
                "payment_date": today,
                "payment_method": RepaymentPayment.PaymentMethod.UPI,
                "payment_recipient": RepaymentPayment.PaymentRecipient.ORGANIZATION,
                "verification_status": RepaymentPayment.VerificationStatus.VERIFIED,
                "recorded_by": employee,
                "verified_by": employee,
                "notes": "Seeded verified demo payment",
            },
        )

        plan = Plan.objects.get(code="starter")
        subscription, _ = Subscription.objects.update_or_create(
            organization=organization,
            defaults={
                "plan": plan,
                "Subscriptioncode": "DEMO-STARTER-001",
                "billing_cycle": Subscription.BillingCycle.MONTHLY,
                "status": Subscription.Status.ACTIVE,
                "start_date": now - timedelta(days=7),
                "end_date": now + timedelta(days=23),
                "next_billing_date": today + timedelta(days=23),
            },
        )
        subscription_payment, _ = Payment.objects.update_or_create(
            provider_payment_id="DEMO-PAYMENT-001",
            defaults={
                "subscription": subscription,
                "amount": plan.monthly_price,
                "currency": organization.currency,
                "provider": "demo",
                "invoice_reference": "DEMO-INVOICE-001",
                "status": Payment.Status.SUCCEEDED,
                "paid_at": now - timedelta(days=7),
            },
        )
        if subscription.payment_id != subscription_payment.id:
            subscription.payment = subscription_payment
            subscription.save(update_fields=["payment"])

        self.stdout.write(self.style.SUCCESS("Demo workspace is ready (safe to run again)."))
        self.stdout.write(f"Organization: {organization.name} (slug: {organization.slug})")
        self.stdout.write("Accounts (same password for each):")
        for username, role in (
            ("demo_admin", "Organization Admin"),
            ("demo_manager", "Manager"),
            ("demo_teamlead", "Team Lead"),
            ("demo_employee", "General Employee"),
        ):
            self.stdout.write(f"  {role}: {username} / {password}")
        self.stdout.write(
            "Seeded: 1 department, 1 team, customer, lead, 3 tasks, "
            "3 follow-ups, repayment schedule/payment, and active Starter subscription."
        )
