# FINCRM project audit

**Audit date:** 2026-11-19  
**Repository:** `D:\FINCMR`  
**Result:** Core defects were corrected and verified. This report records the inspected paths and remaining gaps; it does not claim that every possible defect has been eliminated.

## Scope and environment

The audit followed the installed Django applications, models, serializers, viewsets, routes, permissions, tenant utilities, migrations, seed commands, and the React application, including its API client, forms, module configuration, dashboards, and routing. The checked domains were accounts, organizations, employees, customers, applications, leads, tasks and follow-ups, communications, documents, finance, subscriptions, permissions, and the AI assistant placeholder.

The repository uses Django 6.1.3, Django REST Framework 3.18.3, SQLite, and a Vite/React 19 frontend. The Python environment also has SimpleJWT, django-filter, and django-cors-headers installed. The frontend package declares ESLint, but the installed `node_modules` has no ESLint executable.

## Verified findings and corrections

| Priority | Root cause | Correction |
|---|---|---|
| High | Low-privilege users could receive dashboard/report work querysets containing unassigned records. Repayment dashboard queries also needed reporting-scope filters. | Work metrics now require a staff profile and apply organization and hierarchy scope. Dashboard schedules are scoped to the user’s department, team, or employee. Inactive staff profiles are denied tenant API access. |
| High | Active-role context did not reliably support multiple employee roles and needed a hard ceiling against role-header elevation. | Assigned employee-level roles can be selected with `X-Active-Role`; reserved administrator, manager, team-lead, and portal roles are excluded from employee assignments. The header cannot raise an employee above level 30. |
| High | Staff assignment relationships accepted inactive or out-of-scope manager, team, employee, or department references; some partial transfers could split department/team relationships. | Backend validation now checks organization, active status, hierarchy scope, department/team consistency, and reporting-employee consistency. Assignment dropdown endpoints support active-only options; the frontend filters dependent team and team-lead choices when a department changes. |
| High | Application-to-lead conversion needed an authoritative entitlement check and stronger duplicate handling. Lead qualification also had to remain distinct from application qualification. | Conversion is transactional, links the existing customer and application, assigns the responsible employee, starts the lead at New, checks the active plan’s lead cap, and returns the existing lead on repeat requests. Lead qualification remains blocked until disbursement and repayment schedule requirements are met. Independent lead creation remains disabled by policy. |
| High | Payment records could be edited or deleted after submission, and simultaneous reviewers could act on stale Pending state. The same employee could review their own receipt. | Receipt records are immutable after submission; corrections must be rejected and re-entered. Review rechecks Pending state under a lock and prevents self-review. Historical payment dates remain valid; future payment dates are rejected using the organization timezone. |
| Medium | Customer owner changes had no dedicated assignment history. | Added `CustomerAssignmentHistory`, transactional initial/reassignment logging, a tenant-scoped history action, and frontend action. No historical rows are fabricated for assignments that predate the migration. |
| Medium | Upload validation trusted browser-supplied MIME metadata; document archive existed only at the API layer. | Documents and payment proofs now use size and PDF/JPEG/PNG signature checks. Added a permission-checked document archive action and frontend control. |
| Medium | Task relationships used incorrect ownership lookups for leads, task recipient validation was inconsistent, and date handling did not consistently use organization timezones. | Task/follow-up relationship and active-recipient checks were corrected; new tasks reject past dates while overdue-task edits remain possible; follow-ups reject new/past reschedules and validate meeting data. Organization-local parsing and “today” handling are shared by relevant endpoints and forms. |
| Medium | Interactions, attendees, and message drafts were not consistently restricted to the author’s reporting scope; some related IDs could describe mismatched records. | Added shared interaction scoping, scoped attendee listing/creation, active attendee checks, message-draft scope checks, and validation that lead/customer/application references agree. Attendee results have stable ordering. |
| Medium | Report metrics used legacy lead conversion data or reused the same query for monthly, range, and all-time values. | Pipeline and report metrics now use the current lead status and calculate month-to-date, selected-range, and all-time verified payments separately. |
| Medium | The shared Django admin accepted organization staff carrying `is_staff`; settings contained permissive development security defaults and a misspelled mail setting. | Django admin access is limited to active superusers. CORS now uses an explicit local development allowlist; production requires configured secret key and hosts. `EMAIL_BACKEND` is read from the environment. |
| Medium | Search was performed only on the loaded page, and option-loading failures were hidden in forms. | Resource search now uses backend search parameters; missing dropdown data and request errors are visible. Dependent choices clear incompatible selections. |

Additional serializer checks cover customer/application/lead associations, active assignment eligibility, password validators, valid organization timezones, and task history recording. The new behavior is covered by regressions in the relevant app test modules.

## Requirements coverage

| Domain | Status | Evidence / limits |
|---|---|---|
| Accounts and roles | Improved; partial | Password changes use Django validators; role selection and inactive-profile access are guarded. JWT login/refresh, logout, and account activation lifecycle were not exhaustively exercised end to end. User `is_active` remains separate from employee employment status. |
| Organizations and hierarchy | Improved; tested | Tenant isolation and manager/team-lead/employee reporting paths are covered; department/team/manager assignments validate relationships. Hierarchy is still primarily encoded as fixed numeric levels and endpoint-specific checks rather than consistently enforced from role permission records. |
| Employees | Improved; tested | Onboarding limits, active dropdowns, assignment history, valid in-scope transfers, and rejection of out-of-scope transfers are covered. |
| Customers | Improved; partial | Existing customer/interactions tests pass; initial and changed owners are recorded. Existing assignment history cannot be reconstructed and is not backfilled. |
| Applications and leads | Improved; tested | Application creation, qualification, conversion, repeat conversion, lead cap, and premature lead qualification are covered. Disbursement still requires the existing accepted-document/checklist workflow. |
| Tasks and follow-ups | Improved; partial | Task date and scope checks are covered. There is no dedicated follow-up history model, so follow-up edits do not have the same audit trail as task/application/lead changes. |
| Communications | Improved; partial | Interaction/attendee/draft tenant and reporting scope are enforced. Draft approval does not send an email, SMS, or WhatsApp message; no delivery provider is configured. |
| Documents | Improved; partial | Upload signature/size validation, review, archive, and access-log paths exist. There is no antivirus scan or external object-storage policy in this repository. |
| Finance | Improved; partial | Decimal-based loan calculations and repayment schedule/payment paths exist; payment records are immutable and reviewable. The code calculates an amortizing/reducing-balance EMI; no approved finance policy for flat-rate or alternative methods was found. SQLite does not provide effective `select_for_update` row locking for production concurrency guarantees. |
| Subscriptions | Improved; partial | Employee and lead limits are centralized and enforced at onboarding/conversion. The subscribe flow currently records a `MANUAL` payment as `succeeded` and activates the subscription without a payment-provider confirmation. Do not treat this as a production payment integration. |
| AI assistant | Gap | The installed app is a placeholder; there is no implemented assistant model/API or provider integration. |

## Database and migration safety

Added migration [`0006_customerassignmenthistory.py`](../backend/aron_fincrm/customers/migrations/0006_customerassignmenthistory.py), which only creates the new assignment-history table and adds no destructive data operation. The migration was generated and checked, but was **not applied to the working SQLite database**. Apply it in the intended deployment after reviewing the deployment backup procedure before using the new customer-history endpoint.

The existing database was not changed. Its SHA-256 remains `BB193C1F2D46EE6502B0DE06A12FFCAA57F4D334D097BEA0F3C4FC8F67B72CD8`. A verified copy is stored at [`fincrm-db-before-audit-2026-11-19.sqlite3`](</C:/Users/ayyap/.codex/visualizations/2026/11/19/01a1f336-7f37-7c42-a0a1-04de14ad22bd/fincrm-db-before-audit-2026-11-19.sqlite3>) with the same hash.

## Verification

- `manage.py test`: **29 tests passed** using Django’s temporary test database, including task recipient reassignment.
- `manage.py check`: passed with no issues.
- `manage.py makemigrations --check --dry-run`: no ungenerated model changes.
- `git diff --check`: passed; Git printed only line-ending conversion notices for edited Python files.
- `npm run build`: passed after the frontend changes.
- `npm run lint`: could not run because `eslint` is declared in `package.json` but missing from `node_modules` (`eslint` command not found).

The tests run against SQLite and do not establish production-grade concurrent locking or external integrations.

## Remaining work before production

1. Apply the customer history migration through the deployment process after taking a deployment backup.
2. Integrate a real payment provider and make subscription activation depend on verified payment callbacks rather than the current manual-success path.
3. Choose and document the organization’s EMI/interest method with finance stakeholders; add provider-specific calculation tests before changing it.
4. Use a database with row-level locking for concurrent payment and workflow operations.
5. Implement and authorize the AI assistant and outbound communications integrations before presenting those features as active.
6. Add follow-up change history, malware scanning, and full endpoint-by-endpoint role-permission review, especially where the project still uses fixed hierarchy thresholds.
7. Restore/install the declared frontend lint tooling and run the lint script in CI.
