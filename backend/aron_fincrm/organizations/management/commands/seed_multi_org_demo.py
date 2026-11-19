from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Manager, TeamLead
from applications.models import FinancialApplication
from customers.models import Customer
from employes.models import Employee
from finance.models import RepaymentPayment, RepaymentSchedule
from leads.models import Lead
from organizations.models import Department, Organization, Team
from permitions.models import Role
from tasks.models import CostomerFollowUp, LeadFollowUp, Task, applicationFollowUp


PASSWORD = "FinCRM-Demo-2026!"
ORGANIZATIONS = (
    {"prefix": "north", "slug": "fincrm-north-demo", "name": "Northstar Finance Demo", "state": "Maharashtra", "cities": ["Pune", "Mumbai", "Nashik", "Nagpur"]},
    {"prefix": "south", "slug": "fincrm-south-demo", "name": "Southern Cross Finance Demo", "state": "Karnataka", "cities": ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi"]},
)
FIRST_NAMES = ["Aarav", "Ananya", "Ishaan", "Meera", "Kabir", "Diya", "Rohan", "Priya", "Arjun", "Kavya", "Neel", "Sana", "Vikram", "Aditi", "Dev"]
LAST_NAMES = ["Sharma", "Patel", "Rao", "Iyer", "Singh", "Nair", "Kapoor", "Das", "Joshi", "Khan", "Kulkarni", "Mehta", "Reddy", "Shah", "Pillai"]
STATES = ["Maharashtra", "Karnataka", "Gujarat", "Goa", "Tamil Nadu", "Telangana", "Kerala", "Rajasthan"]
LEAD_STATUSES = [Lead.Status.NEW, Lead.Status.CONTACTED, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED]
APP_STATUSES = [FinancialApplication.Status.SUBMITTED, FinancialApplication.Status.UNDER_REVIEW, FinancialApplication.Status.APPROVED, FinancialApplication.Status.DISBURSED, FinancialApplication.Status.REJECTED]


class Command(BaseCommand):
    help = "Seed two isolated demo organizations with role hierarchies and varied CRM activity. Safe to rerun."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        employee_role = Role.objects.filter(code="general_employee", organization__isnull=True).first()
        if not employee_role:
            self.stderr.write("General Employee role is missing. Run seed_roles_permissions first.")
            return

        today = timezone.localdate()
        now = timezone.now()
        credentials = []
        summaries = []

        for config in ORGANIZATIONS:
            prefix = config["prefix"]
            org, _ = Organization.objects.update_or_create(
                slug=config["slug"],
                defaults={
                    "name": config["name"], "legal_name": config["name"],
                    "email": f"admin@{prefix}-fincrm.test", "phone": f"+91 90000 {10000 if prefix == 'north' else 20000}",
                    "city": config["cities"][0], "state": config["state"], "country": "India",
                    "timezone": "Asia/Kolkata", "currency": "INR", "is_active": True,
                },
            )

            def make_user(username, first, last, role):
                user, _ = User.objects.update_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@{prefix}-fincrm.test", "first_name": first, "last_name": last,
                        "is_active": True, "default_organization": org,
                    },
                )
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
                credentials.append((config["name"], role, username, PASSWORD))
                return user

            admin = make_user(f"{prefix}_admin", "FinCRM", "Admin", "Organization Admin")

            managers = []
            departments = []
            for index in range(3):
                first = FIRST_NAMES[index]
                last = LAST_NAMES[index]
                user = make_user(f"{prefix}_manager{index + 1:02d}", first, last, "Manager")
                manager, _ = Manager.objects.update_or_create(
                    user=user,
                    defaults={
                        "organization": org, "code": f"{prefix.upper()}-MGR-{index + 1:02d}",
                        "work_email": user.email, "designation": f"{['Retail', 'Business', 'Operations'][index]} Manager",
                        "employment_status": Manager.ManagerStatus.ACTIVE, "join_date": today - timedelta(days=400 + index * 30),
                    },
                )
                department, _ = Department.objects.update_or_create(
                    organization=org, name=f"{['Retail Sales', 'Business Finance', 'Customer Operations'][index]}",
                    defaults={"description": f"{config['name']} · department {index + 1}", "manager": manager, "is_active": True},
                )
                managers.append((manager, user))
                departments.append(department)

            team_leads = []
            teams = []
            for index in range(5):
                manager, manager_user = managers[index % len(managers)]
                department = departments[index % len(departments)]
                first = FIRST_NAMES[(index + 4) % len(FIRST_NAMES)]
                last = LAST_NAMES[(index + 5) % len(LAST_NAMES)]
                user = make_user(f"{prefix}_teamlead{index + 1:02d}", first, last, "Team Lead")
                teamlead, _ = TeamLead.objects.update_or_create(
                    user=user,
                    defaults={
                        "organization": org, "code": f"{prefix.upper()}-TL-{index + 1:02d}",
                        "department": department, "manager": manager, "work_email": user.email,
                        "designation": f"Team Lead {index + 1}", "employment_status": TeamLead.teamStatus.ACTIVE,
                        "join_date": today - timedelta(days=250 + index * 12),
                    },
                )
                team, _ = Team.objects.update_or_create(
                    organization=org, name=f"{['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo'][index]} Team",
                    defaults={"department": department, "team_lead": teamlead, "description": f"{config['name']} team {index + 1}", "is_active": True},
                )
                team_leads.append((teamlead, user, manager_user, department))
                teams.append(team)

            employees = []
            for index in range(10):
                team_index = index // 2
                lead_profile, lead_user, _, department = team_leads[team_index]
                team = teams[team_index]
                first = FIRST_NAMES[(index + 8) % len(FIRST_NAMES)]
                last = LAST_NAMES[(index + 9) % len(LAST_NAMES)]
                user = make_user(f"{prefix}_employee{index + 1:02d}", first, last, "Employee")
                employee, _ = Employee.objects.update_or_create(
                    user=user,
                    defaults={
                        "organization": org, "employee_code": f"{prefix.upper()}-EMP-{index + 1:02d}",
                        "department": department, "team": team, "role": employee_role,
                        "work_email": user.email, "work_phone": f"+91 98{prefix == 'south' and '7' or '6'}{index:08d}",
                        "designation": "Customer Relationship Executive", "employment_status": Employee.EmploymentStatus.ACTIVE,
                        "join_date": today - timedelta(days=80 + index * 7),
                    },
                )
                employees.append((employee, user, lead_user, department, team))

            customers = []
            for index in range(15):
                employee, _, _, _, _ = employees[index % len(employees)]
                full_name = f"{FIRST_NAMES[(index + 3) % len(FIRST_NAMES)]} {LAST_NAMES[(index + 7) % len(LAST_NAMES)]}"
                customer, _ = Customer.objects.update_or_create(
                    organization=org, customer_code=f"{prefix.upper()}-CUST-{index + 1:03d}",
                    defaults={
                        "customer_type": Customer.CustomerType.INDIVIDUAL if index % 4 else Customer.CustomerType.BUSINESS,
                        "full_name": full_name, "legal_name": f"{full_name} Enterprises" if index % 4 == 0 else "",
                        "primary_phone": f"+91 9{prefix == 'south' and '7' or '6'}{index + 1:09d}",
                        "email": f"{prefix}.customer{index + 1:02d}@example.test",
                        "preferred_channel": ["phone", "email", "whatsapp", "sms", "other"][index % 5],
                        "city": config["cities"][index % len(config["cities"])], "state": STATES[(index + (0 if prefix == 'north' else 2)) % len(STATES)],
                        "country": "India", "source": ["Referral", "Website", "Branch", "Campaign"][index % 4],
                        "status": [Customer.Status.ACTIVE, Customer.Status.PROSPECT, Customer.Status.INACTIVE][index % 3],
                        "created_by": employee, "assigned_to": employee, "notes": f"{config['name']} sample customer {index + 1}.",
                    },
                )
                customers.append(customer)

            leads = []
            for index in range(30):
                employee, _, _, _, _ = employees[index % len(employees)]
                customer = customers[index % len(customers)]
                lead = Lead.objects.update_or_create(
                    organization=org, lead_code=f"{prefix.upper()}-LEAD-{index + 1:03d}",
                    defaults={
                        "contact_name": customer.full_name, "phone": customer.primary_phone, "email": customer.email,
                        "city": customer.city, "state": customer.state, "assigned_to": employee,
                        "converted_customer": customer if index % 5 == 0 else None,
                        "source": [Lead.Source.REFERRAL, Lead.Source.WEBSITE, Lead.Source.SOCIAL_MEDIA, Lead.Source.CAMPAIGN, Lead.Source.WALK_IN][index % 5],
                        "priority": [Lead.Priority.HIGH, Lead.Priority.MEDIUM, Lead.Priority.LOW][index % 3],
                        "status": LEAD_STATUSES[index % len(LEAD_STATUSES)],
                        "expected_amount": Decimal(75000 + (index * 18750) + (0 if prefix == "north" else 12500)),
                        "currency": "INR", "created_by": employee,
                    },
                )[0]
                leads.append(lead)

            applications = []
            for index in range(15):
                employee, user, _, _, _ = employees[index % len(employees)]
                requested = Decimal(50000 + index * 15000 + (0 if prefix == "north" else 10000))
                application, _ = FinancialApplication.objects.update_or_create(
                    organization=org, application_code=f"{prefix.upper()}-APP-{index + 1:03d}",
                    defaults={
                        "customer": customers[index], "lead": leads[index], "assigned_employee": employee,
                        "status": APP_STATUSES[index % len(APP_STATUSES)], "requested_amount": requested,
                        "approved_amount": requested if index % 5 in (2, 3) else None,
                        "disbursed_amount": requested if index % 5 == 3 else None,
                        "currency": "INR", "submitted_at": now - timedelta(days=index * 3 + 1),
                        "notes": f"{config['name']} application scenario {index + 1}.", "created_by": user,
                    },
                )
                applications.append(application)

            for index, customer in enumerate(customers):
                employee = employees[index % len(employees)][0]
                scheduled = now + timedelta(days=(index % 7) - 3)
                CostomerFollowUp.objects.update_or_create(
                    organization=org, customer=customer, followup_type=["CALL", "EMAIL", "MEETING", "VISIT", "OTHER"][index % 5],
                    defaults={"created_by": employee, "scheduled_at": scheduled, "status": "COMPLETED" if index % 6 == 0 else "PENDING", "notes": f"Customer follow-up #{index + 1}: confirm next steps."},
                )

            for index, lead in enumerate(leads[:20]):
                employee = employees[index % len(employees)][0]
                LeadFollowUp.objects.update_or_create(
                    organization=org, lead=lead, followup_type=["CALL", "EMAIL", "MEETING", "VISIT"][index % 4],
                    defaults={"created_by": employee, "scheduled_at": now + timedelta(days=(index % 9) - 4), "status": "COMPLETED" if index % 5 == 0 else "PENDING", "notes": f"Lead follow-up #{index + 1}: record contact outcome."},
                )

            for index, application in enumerate(applications):
                employee = employees[index % len(employees)][0]
                applicationFollowUp.objects.update_or_create(
                    organization=org, application=application, followup_type=["CALL", "EMAIL", "MEETING"][index % 3],
                    defaults={"created_by": employee, "scheduled_at": now + timedelta(days=(index % 8) - 3), "status": "COMPLETED" if index % 4 == 0 else "PENDING", "notes": f"Application follow-up #{index + 1}: check documents and status."},
                )

            for app_index, application in enumerate(applications):
                if application.status not in (FinancialApplication.Status.APPROVED, FinancialApplication.Status.DISBURSED):
                    continue
                employee = employees[app_index % len(employees)][0]
                installment = (application.requested_amount or Decimal("0")) / Decimal("3")
                for installment_number in range(1, 4):
                    due = today + timedelta(days=(-20, 0, 30)[installment_number - 1] + app_index % 4)
                    status = RepaymentSchedule.Status.PARTIAL if installment_number == 1 and app_index % 2 else RepaymentSchedule.Status.PENDING
                    if installment_number == 1 and app_index % 4 == 0:
                        status = RepaymentSchedule.Status.PAID
                    schedule, _ = RepaymentSchedule.objects.update_or_create(
                        application=application, installment_number=installment_number,
                        defaults={
                            "organization": org, "customer": application.customer, "lead": application.lead,
                            "payment_type": RepaymentSchedule.PaymentType.EMI,
                            "expected_amount": installment.quantize(Decimal("0.01")), "due_date": due,
                            "status": status, "notes": f"Demo installment {installment_number} for {application.application_code}.",
                        },
                    )
                    if installment_number == 1 and app_index % 3 != 1:
                        amount = installment.quantize(Decimal("0.01")) if status == RepaymentSchedule.Status.PAID else (installment / 2).quantize(Decimal("0.01"))
                        RepaymentPayment.objects.update_or_create(
                            repayment_schedule=schedule, transaction_reference=f"{prefix.upper()}-PAY-{app_index + 1:03d}-{installment_number}",
                            defaults={
                                "organization": org, "amount": amount, "payment_date": today - timedelta(days=app_index % 20),
                                "payment_method": [RepaymentPayment.PaymentMethod.UPI, RepaymentPayment.PaymentMethod.BANK, RepaymentPayment.PaymentMethod.CASH][app_index % 3],
                                "payment_recipient": RepaymentPayment.PaymentRecipient.ORGANIZATION,
                                "verification_status": RepaymentPayment.VerificationStatus.VERIFIED,
                                "recorded_by": employee, "verified_by": employee,
                                "notes": f"Seeded payment for {application.application_code}.",
                            },
                        )
                    elif installment_number == 2 and app_index % 3 == 1:
                        RepaymentPayment.objects.update_or_create(
                            repayment_schedule=schedule, transaction_reference=f"{prefix.upper()}-PENDING-{app_index + 1:03d}",
                            defaults={
                                "organization": org, "amount": (installment / 2).quantize(Decimal("0.01")), "payment_date": today,
                                "payment_method": RepaymentPayment.PaymentMethod.UPI,
                                "payment_recipient": RepaymentPayment.PaymentRecipient.ORGANIZATION,
                                "verification_status": RepaymentPayment.VerificationStatus.PENDING,
                                "recorded_by": employee, "verified_by": None, "notes": "Awaiting payment review.",
                            },
                        )

            for index in range(3):
                manager, manager_user = managers[index]
                Task.objects.update_or_create(
                    organization=org, title=f"{config['name']} manager review {index + 1}",
                    defaults={
                        "description": f"Manager task {index + 1} across the managed department.", "assigned_by_user": admin,
                        "assigned_to_user": manager_user, "department": departments[index], "priority": Task.Priority.HIGH if index == 0 else Task.Priority.MEDIUM,
                        "status": [Task.Status.PENDING, Task.Status.IN_PROGRESS, Task.Status.COMPLETED][index],
                        "start_date": now - timedelta(days=2), "due_date": now + timedelta(days=index - 1),
                    },
                )
            for index, (teamlead, lead_user, manager_user, department) in enumerate(team_leads):
                Task.objects.update_or_create(
                    organization=org, title=f"{config['name']} team lead follow-up review {index + 1}",
                    defaults={
                        "description": f"Review team pipeline and follow-ups for team {index + 1}.", "assigned_by_user": manager_user,
                        "assigned_to_user": lead_user, "assigned_by_manager": teamlead.manager, "department": department,
                        "team": teams[index], "priority": Task.Priority.MEDIUM,
                        "status": [Task.Status.PENDING, Task.Status.IN_PROGRESS, Task.Status.COMPLETED][index % 3],
                        "start_date": now - timedelta(days=1), "due_date": now + timedelta(days=(index % 3) - 1),
                    },
                )
            for index, (employee, _, lead_user, department, team) in enumerate(employees):
                for task_index in range(2):
                    lead = leads[(index * 2 + task_index) % len(leads)]
                    customer = customers[(index + task_index) % len(customers)]
                    Task.objects.update_or_create(
                        organization=org, title=f"{config['name']} employee {index + 1} task {task_index + 1}",
                        defaults={
                            "description": f"Customer servicing task {task_index + 1} assigned to employee {index + 1}.",
                            "assigned_by_user": lead_user, "assigned_to_user": employee.user, "assigned_by_teamlead": team_leads[index // 2][0],
                            "assigned_to": employee, "department": department, "team": team,
                            "related_customer": customer, "related_lead": lead,
                            "related_application": applications[index % len(applications)],
                            "priority": [Task.Priority.LOW, Task.Priority.MEDIUM, Task.Priority.HIGH, Task.Priority.URGENT][(index + task_index) % 4],
                            "status": [Task.Status.PENDING, Task.Status.IN_PROGRESS, Task.Status.COMPLETED][(index + task_index) % 3],
                            "start_date": now - timedelta(days=task_index + 1), "due_date": now + timedelta(days=(index + task_index) % 5 - 2),
                        },
                    )

            summaries.append(f"{org.name}: 1 admin, 3 managers, 5 team leads, 10 employees, 15 customers, 30 leads, 15 applications, 50 follow-ups, and repayment/task data.")

        self.stdout.write(self.style.SUCCESS("Multi-organization demo data is ready (safe to rerun)."))
        for summary in summaries:
            self.stdout.write(f"  {summary}")
        self.stdout.write(f"All seeded users share this password: {PASSWORD}")
        self.stdout.write("Credentials:")
        for org_name, role, username, password in credentials:
            self.stdout.write(f"  {org_name} | {role} | {username} | {password}")
