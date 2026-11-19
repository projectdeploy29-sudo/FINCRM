from django.core.management.base import BaseCommand
from permitions.models import Permission, Role, RolePermission


class Command(BaseCommand):
    help = "Seeds initial system permissions and standard roles, including Sales Analyst and lead operations roles."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding system permissions..."))

        # Define permissions (module, action, codename, description)
        permissions_data = [
            # Organizations
            ("organizations", "view", "organizations:view", "View organization profile"),
            ("organizations", "manage", "organizations:manage", "Manage organization settings"),

            # Departments
            ("departments", "view", "departments:view", "View departments"),
            ("departments", "create", "departments:create", "Create department"),
            ("departments", "edit", "departments:edit", "Edit department"),
            ("departments", "delete", "departments:delete", "Delete department"),

            # Teams
            ("teams", "view", "teams:view", "View teams"),
            ("teams", "create", "teams:create", "Create team"),
            ("teams", "edit", "teams:edit", "Edit team"),
            ("teams", "delete", "teams:delete", "Delete team"),

            # Employees & Staff
            ("employees", "view", "employees:view", "View staff directory"),
            ("employees", "create", "employees:create", "Onboard employees and staff"),
            ("employees", "edit", "employees:edit", "Update employee profiles"),
            ("employees", "delete", "employees:delete", "Terminate/deactivate employees"),

            # Roles & Permissions
            ("roles", "view", "roles:view", "View roles"),
            ("roles", "manage", "roles:manage", "Configure role permissions"),

            # Customers
            ("customers", "view", "customers:view", "View customer profiles"),
            ("customers", "create", "customers:create", "Create new customers"),
            ("customers", "edit", "customers:edit", "Update customer details"),
            ("customers", "change_status", "customers:change_status", "Update customer status"),
            ("customers", "delete", "customers:delete", "Delete/archive customers"),

            # Leads
            ("leads", "view", "leads:view", "View leads pipeline"),
            ("leads", "create", "leads:create", "Capture/create new leads"),
            ("leads", "edit", "leads:edit", "Edit lead details and priority"),
            ("leads", "assign", "leads:assign", "Assign leads to team members"),
            ("leads", "convert", "leads:convert", "Convert qualified leads to customers"),
            ("leads", "delete", "leads:delete", "Delete leads"),

            # Applications (Loans & Insurance)
            ("applications", "view", "applications:view", "View financial applications"),
            ("applications", "create", "applications:create", "Submit loan/insurance application"),
            ("applications", "edit", "applications:edit", "Modify application info"),
            ("applications", "review", "applications:review", "Review application documents & KYC"),
            ("applications", "approve", "applications:approve", "Approve financial application"),
            ("applications", "disburse", "applications:disburse", "Mark application disbursed"),
            ("applications", "reject", "applications:reject", "Reject application"),

            # Documents & KYC
            ("documents", "view", "documents:view", "View uploaded documents"),
            ("documents", "upload", "documents:upload", "Upload customer/application documents"),
            ("documents", "download", "documents:download", "Download document files"),
            ("documents", "verify", "documents:verify", "Verify and accept submitted documents"),
            ("documents", "reject", "documents:reject", "Reject uploaded document"),

            # Finance & Repayments
            ("finance", "view_schedules", "finance:view_schedules", "View repayment EMI/premium schedules"),
            ("finance", "manage_schedules", "finance:manage_schedules", "Generate or update schedules"),
            ("finance", "record_payment", "finance:record_payment", "Record customer payment collection"),
            ("finance", "verify_payment", "finance:verify_payment", "Verify payment receipt"),

            # Tasks
            ("tasks", "view", "tasks:view", "View tasks"),
            ("tasks", "create", "tasks:create", "Create tasks"),
            ("tasks", "assign", "tasks:assign", "Assign tasks to team members"),
            ("tasks", "update", "tasks:update", "Update task progress and completion"),
            ("tasks", "delete", "tasks:delete", "Cancel/delete tasks"),

            # Follow-ups
            ("followups", "view", "followups:view", "View follow-up agenda"),
            ("followups", "create", "followups:create", "Schedule new follow-ups"),
            ("followups", "update", "followups:update", "Complete or reschedule follow-ups"),

            # Dashboards
            ("dashboards", "admin", "dashboards:admin", "Access Org Admin analytics dashboard"),
            ("dashboards", "manager", "dashboards:manager", "Access Manager team performance dashboard"),
            ("dashboards", "teamlead", "dashboards:teamlead", "Access Team Lead dashboard"),
            ("dashboards", "employee", "dashboards:employee", "Access Employee My-Day workspace"),
        ]

        created_perms = 0
        perm_map = {}
        for module, action, codename, desc in permissions_data:
            perm_obj, created = Permission.objects.update_or_create(
                codename=codename,
                defaults={
                    "module": module,
                    "action": action,
                    "description": desc,
                }
            )
            perm_map[codename] = perm_obj
            if created:
                created_perms += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(permissions_data)} permissions ({created_perms} newly created)."))

        # Define System Roles
        roles_config = [
            {
                "name": "Organization Admin",
                "code": "org_admin",
                "description": "Full administrative privileges over the organization",
                "is_system_role": True,
                "permissions": list(perm_map.keys()),  # All permissions
            },
            {
                "name": "Manager",
                "code": "manager",
                "description": "Department and team management, task assignment, and department analytics",
                "is_system_role": True,
                "permissions": [
                    "departments:view",
                    "teams:view", "teams:create", "teams:edit",
                    "employees:view", "employees:create", "employees:edit",
                    "customers:view", "customers:create", "customers:edit", "customers:change_status",
                    "leads:view", "leads:create", "leads:edit", "leads:assign", "leads:convert",
                    "applications:view", "applications:create", "applications:edit", "applications:review", "applications:approve", "applications:reject",
                    "documents:view", "documents:upload", "documents:download", "documents:verify", "documents:reject",
                    "finance:view_schedules", "finance:record_payment", "finance:verify_payment",
                    "tasks:view", "tasks:create", "tasks:assign", "tasks:update",
                    "followups:view", "followups:create", "followups:update",
                    "dashboards:manager",
                ],
            },
            {
                "name": "Team Lead",
                "code": "team_lead",
                "description": "Team oversight, lead assignment, and task delegation",
                "is_system_role": True,
                "permissions": [
                    "teams:view",
                    "employees:view",
                    "customers:view", "customers:create", "customers:edit", "customers:change_status",
                    "leads:view", "leads:create", "leads:edit", "leads:assign", "leads:convert",
                    "applications:view", "applications:create", "applications:edit",
                    "documents:view", "documents:upload", "documents:download", "documents:verify", "documents:reject",
                    "applications:review", "applications:approve", "applications:disburse", "applications:reject",
                    "finance:view_schedules", "finance:manage_schedules", "finance:record_payment", "finance:verify_payment",
                    "tasks:view", "tasks:create", "tasks:assign", "tasks:update",
                    "followups:view", "followups:create", "followups:update",
                    "dashboards:teamlead",
                ],
            },
            {
                "name": "General Employee",
                "code": "general_employee",
                "description": "Customer sourcing, lead management, and application follow-ups",
                "is_system_role": True,
                "permissions": [
                    "customers:view", "customers:create", "customers:edit", "customers:change_status",
                    "leads:view", "leads:create", "leads:edit", "leads:convert",
                    "applications:view", "applications:create", "applications:edit",
                    "documents:view", "documents:upload", "documents:download",
                    "finance:view_schedules", "finance:record_payment",
                    "tasks:view", "tasks:update",
                    "followups:view", "followups:create", "followups:update",
                    "dashboards:employee",
                ],
            },
        ]

        obsolete_employee_roles = ('doc_officer', 'document_verification_officer', 'finance_analyst', 'financial_analyst', 'sales_analyst')
        from employes.models import Employee
        general_employee_role = Role.objects.filter(code='general_employee', organization__isnull=True).first()
        if general_employee_role:
            Employee.objects.filter(role__code__in=obsolete_employee_roles).update(role=general_employee_role)
            for employee in Employee.objects.filter(additional_roles__code__in=obsolete_employee_roles).distinct():
                employee.additional_roles.remove(*employee.additional_roles.filter(code__in=obsolete_employee_roles))
        Role.objects.filter(organization__isnull=True, code__in=obsolete_employee_roles).delete()

        for role_data in roles_config:
            role_obj, _ = Role.objects.update_or_create(
                code=role_data["code"],
                organization=None,  # Global system templates
                defaults={
                    "name": role_data["name"],
                    "description": role_data["description"],
                    "is_system_role": True,
                }
            )

            # Map permissions
            assigned_count = 0
            for perm_code in role_data["permissions"]:
                if perm_code in perm_map:
                    RolePermission.objects.get_or_create(
                        role=role_obj,
                        permission=perm_map[perm_code],
                    )
                    assigned_count += 1

            self.stdout.write(self.style.SUCCESS(f"Configured role '{role_data['name']}' with {assigned_count} permissions."))

        self.stdout.write(self.style.SUCCESS("All system permissions and roles successfully seeded!"))
