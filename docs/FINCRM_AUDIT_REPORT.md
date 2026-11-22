# FINCRM production readiness audit

**Audit date:** 2026-11-22
**Repository:** `D:\FINCMR`
**Branch:** `codex/fincrm-complete-audit-2026-11-22`
**Result:** Safe code repairs and regression checks are complete. **Do not deploy or enable paid checkout yet.** Business policy, catalog prices, migration risks, and deployment verification remain unresolved.

## Scope and method

The review builds on the earlier 235-file audit and its documented repairs. This pass reviewed subscription and entitlement code, plan migrations and seed behavior, payment verification, settings and dependencies, the Enterprise inquiry workflow, frontend plan UI, and the current read-only migration plan. No production credentials were read or copied. No database migration or seed command was run against the checked SQLite database. Payment, SMTP, and database-provider interactions in tests were mocked or used Django's in-memory test facilities; no real payment or email was sent.

## 1. Issues resolved

| Area | Repair |
|---|---|
| Paid plan pricing | Added `SUBSCRIPTION_CHECKOUT_ENABLED=false` by default. The API masks prices and reports checkout unavailable until the flag is enabled and both cycle prices are positive. The frontend keeps all plans, features, limits, and descriptions visible, shows that pricing is pending, and disables paid checkout buttons. The API rejects checkout while disabled. No price or Razorpay plan ID was invented. |
| Seed safety | Changed `seed_plans` to `get_or_create`; it no longer overwrites existing catalog prices/features. Fresh installs still receive the existing placeholder values, so checkout remains disabled until an operator updates and verifies the catalog. |
| Enterprise inquiry | Reused the existing inquiry table and added status, internal notes, quote amount/cycle, optional organization association, idempotency key, and payment-link tracking. Backend validation covers required fields, email, 7–15 digit phone formats, HTTP(S) website/LinkedIn URLs, and note length. |
| Inquiry spam and duplicates | Added a honeypot, a 10-per-hour scoped API throttle, a client idempotency key, and a 15-minute duplicate window for matching email/phone/organization. Duplicate requests return an acknowledgment without creating another inquiry or sending duplicate notifications. |
| Inquiry email behavior | The saved inquiry is retained if SMTP fails. A normal valid submission attempts the two requested messages: customer confirmation and administrator notification. Only the administrator receives the submitted details. Admins can retry missing notifications from Django Admin. The configured admin address is not returned by the API. |
| Enterprise review and payment | Added Django Admin search, status filtering/editing, internal notes, quote fields, and actions to retry notifications or create an approved custom checkout. Enterprise cannot use the public plan checkout endpoint. The admin action creates an order only after status is **Agreement reached**, a positive agreed amount, and a billing cycle are set. It emails a token-protected 48-hour checkout link. Payment verification rechecks approval and the quoted amount/cycle/email; stale or closed quotes cannot be paid. A registration link is issued only after successful payment verification. |
| Backend feature enforcement | Added server-side enforcement of the explicit `custom_roles` feature for role creation and updates. Active Starter plans cannot bypass this through direct role API calls; a plan that explicitly enables the feature can. Employee and lead caps continue to be enforced by their backend serializers/conversion path for active/trial subscriptions. |
| PostgreSQL readiness | Added explicit opt-in PostgreSQL environment configuration, connection health checks, SSL mode, connection-age and port validation, plus the Psycopg 3 binary dependency. SQLite remains the default. No connection or database conversion was attempted. Django's current database documentation supports Psycopg 3.1.12+; the declared `>=3.2,<4` range is compatible. ([Django database docs](https://docs.djangoproject.com/en/6.1/ref/databases/)) |
| Migration | Added `subscriptions.0007_enterprise_inquiry_review_and_checkout.py` for the new fields and relation. Existing migrations and migration history were left intact. |

The earlier audit repairs also remain in the working tree: tenant validation, organization timezone boundaries, pipeline query batching, auth refresh/logout, API-origin checks, expired-subscription display, receipt validation, and navigation/accessibility changes.

## 2. Issues still remaining (severity)

### Critical

- **Paid prices are not approved.** Starter, Growth, and Professional migration/seed values remain placeholder rupee amounts. Checkout is disabled and catalog price fields are hidden. Supply all six monthly/yearly INR prices, update the database plan rows through the approved release process, verify API output, then enable checkout. The flag alone does not change catalog values.
- **No-plan and failed-renewal access policy is unanswered.** `active_subscription()` ignores missing, expired, cancelled, and past-due subscriptions. `enforce_resource_limit()` currently treats those cases as no configured cap and permits employee/lead writes. Tests document this legacy behavior; it was not changed because choosing deny, read-only, free-tier, or grace access is a business decision. `Subscription` has no failed state; `PlanCheckout.FAILED` represents order creation failure, not a failed renewal.
- **Production migration data risks require a target-database decision.** Customer-tag links and legacy AI records may be lost if the identified migrations are applied to an affected existing database. Existing production migration state/data was not available for inspection.

### High

- **Production PostgreSQL is configured but not connected or rehearsed.** There is no verified production server, staging import, concurrent-payment test, or backup restore. SQLite does not provide the row-level locking needed by the receipt and resource-limit concurrency paths.
- **Recurring billing is incomplete.** Razorpay Orders are used, not Razorpay Subscriptions. Monthly/yearly periods are fixed at 30/365 days. There is no provider webhook, automatic renewal, renewal failure/retry, grace-period workflow, or payment reconciliation job. Cancellation is immediate.
- **Plan changes are immediate.** A verified purchase for an existing organization cancels its previous active/trial subscription and activates the new plan at once. There is no proration, end-of-period downgrade, or refund workflow.
- **Several plan limits/features have no enforceable definition.** The database models only employee and lead numeric caps; customer and storage limits do not exist. `custom_roles` is now enforced. Other flags such as `advanced_reports`, `priority_support`, and `dedicated_support` lack a mapped backend feature workflow or product policy.
- **Migration `subscriptions.0005` is irreversible and drops legacy tables.** It removes `ai_assistant_aimessage`/`ai_assistant_aiconversation` and deletes their migration-history rows. Any retained chat data must be exported/restored manually from a verified backup before applying it to a database where it is pending.
- **Migration `customers.0003` can lose tag links.** It removes `Customertag.costomer` and adds `customer` against the same `costomer_id` column. On databases where the field is still present, export and validate tag/customer pairs before applying, rehearse on a clone, then verify/restore the relationships. The inspected local database marks this migration applied; its customer data was not read.
- **Migration `subscriptions.0006` can overwrite plan rows.** Its `RunPython` uses `update_or_create` with placeholder prices and default feature/limit data. It is marked applied locally; check each deployment. On targets where pending, back up the plan catalog, rehearse and diff the result, and restore only approved catalog values before checkout is enabled.
- **Migration `subscriptions.0004` removes the legacy `max_applications_per_month` plan column.** Any customized cap values in an existing database are not retained by the current model. It is marked applied locally; verify whether those values matter to a target before rollout and preserve a catalog export.
- **Public inquiry email delivery is not guaranteed by application tests.** The API persists on delivery failure and exposes an admin retry action; SMTP/backend acceptance and exactly-once delivery cannot be established without provider-side delivery tracking. Configure `ENTERPRISE_INQUIRY_ADMIN_EMAIL` and the Django email backend, then verify both messages in a non-production mail test.

### Medium

- **ESLint did not run.** `eslint` is declared as version 10 with a flat `eslint.config.js`; ESLint's official migration docs state flat config is the default from v9. The executable is absent from `node_modules`. The previous offline install stopped because `zod-validation-error@4.0.2` is missing from the npm cache. Restore frontend dependencies in an environment with package access, then run `npm run lint`. ([ESLint configuration docs](https://eslint.org/docs/latest/use/configure/configuration-files), [migration guide](https://eslint.org/docs/latest/use/configure/migration-guide))
- **Inquiry rate limits need a shared production cache.** The endpoint is throttled at 10/hour per client IP. Configure a shared cache (for example, Redis) across workers to make the throttle consistent in production.
- **Enterprise admin workflow was backend-tested, not browser-tested.** The model admin is staff-only and registered for search/filter/edit/action. The order action uses a mocked provider in tests; test the complete admin and checkout UX in a staging environment.
- **Document and communications workflows remain incomplete.** Documents have models without a customer-facing API/UI or upload validation. Communications drafts are not delivery; interaction models have no routed workflow. No end-to-end test can cover absent APIs/providers.
- **Frontend verification is build-only.** No browser automation or manual cross-browser checks were run for modals, mobile layout, checkout callbacks, or registration deep links.
- **Potential query-volume and tenant-integrity risks remain.** Some serializers perform per-record aggregates/lookups, and the schema does not enforce tenant equality across all foreign-key relationships. Profile query counts and direct-ORM integrity protections against production-sized fixtures.
- **Several historical data migrations need row-level preflight.** `applications.0003` collapses unrecognized checklist statuses to pending and has a partial reverse; `applications.0007` performs one-way financial backfills; and `finance.0002` can fail on duplicate installments. `whatsapp.0002` leaves seeded templates on reverse. These migrations are applied in the local history but source rows were not audited.

### Low

- **Browser tokens remain in `localStorage`.** Logout revokes refresh tokens, but successful same-origin script injection can still read access/refresh tokens. A reviewed HttpOnly-cookie/session strategy and a restrictive CSP would reduce this exposure.
- **Production hardening needs explicit deployment values.** Set `DJANGO_DEBUG=false`, a private secret, allowed hosts/origins, HTTPS/HSTS, secure cookie settings, database and media backups, restore testing, and monitoring. Do not use development defaults.

## 3. Subscription and payment findings

| State | Current behavior |
|---|---|
| Active, unexpired | Employee and lead caps are enforced server-side. Explicit custom-role feature is enforced on create/update. |
| Trialing, unexpired | Same limit/feature resolution as active. |
| Past due | Not treated as active; writes currently have no subscription limit. There is no payment-renewal state machine. |
| Cancelled | Cancellation endpoint marks the subscription cancelled immediately. Writes currently have no plan cap. Period-end cancellation policy needs confirmation. |
| Expired | Current-subscription response reports no active plan; writes currently have no plan cap. |
| No subscription | Writes currently have no plan cap. This is unresolved policy, not an intentional entitlement grant. |
| Failed payment | Order-creation failure is recorded as a failed checkout. Payment provider failures are not persisted as a renewal state; there is no webhook/retry workflow. |

Customer caps, storage caps, plan-specific customer access, and advanced report enforcement are absent. Plan/month/year amount consistency is maintained by reading the selected amount from the database for both displayed API price and order creation, but checkout remains disabled until real values are entered. Razorpay verification checks signature and fetched order/payment status, captured amount, and currency. Verification/activation is idempotent for the same successful payment. No real Razorpay request was made.

## 4. Migration safety and applied history

The operation scan covered **56 migration modules** and looked for data/SQL operations, model/field removals, renames, and constraints. The migration plan was read without applying migrations. The checked local SQLite database reports application migrations through `subscriptions.0006` as applied; the newly added `subscriptions.0007` is pending. SimpleJWT blacklist migrations are also pending locally. No migration, reset, or seed command touched the checked SQLite database. Django's test runner did apply migrations, including `0007`, only to its disposable in-memory test database.

The operation scan also found these data/constraint behaviors:

- `applications.0003` changes `approved` checklist statuses to `accepted`, and maps every other value outside `accepted/rejected` to `pending`. Its reverse only changes `accepted` back to `approved`, so unknown legacy values are not recoverable. `applications.0007` backfills `net_disbursed_amount` from `disbursed_amount` and sets a missing annual interest rate to zero for disbursed applications; its reverse is a no-op. Both are applied locally, but affected rows were not read or validated.
- `finance.0002` adds uniqueness for `(application, installment_number)`. Existing duplicates would stop migration; check with a grouped duplicate query and resolve only after a business-approved reconciliation.
- `whatsapp.0002` inserts default templates with `get_or_create`; its registered reverse is a no-op, so reversing does not remove the inserted templates. This is non-destructive but not a clean rollback.
- `makemigrations --check` verifies model/migration state, not existing-row correctness or the data transformations above. The migration graph has no detected model drift or conflicting leaf migration in the checked tree.

Release procedure for existing databases:

1. Take encrypted, verified backups of the database and uploaded media; test restoration. Record migration state and row counts from each target.
2. Clone each target and rehearse pending migrations. Export affected customer-tag pairs before `customers.0003`; export legacy AI tables before `subscriptions.0005`; save the plan catalog including the removed application cap before `subscriptions.0004`/`0006`; check checklist values before `applications.0003`; compare financial amounts/rates before `applications.0007`; and check duplicate installments before `finance.0002`.
3. Compare table/column/index/FK state and business row counts before and after. Restore/reconcile tag relationships and approved plan/catalog values on the clone, then verify again.
4. Stop if a target contains valuable legacy chat data and there is no approved export/recovery plan. Do not fake migration history or delete migration rows to skip work.
5. Schedule reviewed migration execution and a rollback window. Keep original backups until application/API checks and financial reconciliation succeed.

Fresh installs and existing database upgrades both receive placeholder plan rows from the historical catalog seed. Keep checkout disabled until a human verifies the final data. Never edit the already-existing migration files to change a migration that may have run elsewhere.

## 5. Database production readiness

SQLite remains the development default. PostgreSQL is appropriate for multi-tenant production writes, transactional row locking, concurrency, and operational backups. Configuration requires explicit `DB_ENGINE=postgresql`, DB name/user/password/host, validated port, SSL mode (defaults to `require`), connection age, and health checks. `psycopg[binary]>=3.2,<4` was added. Unit tests cover config parsing but no PostgreSQL driver install, connection, schema migration, or data import was performed.

Before switching, provision a protected PostgreSQL instance, rehearse export/import on a clone, compare row counts and constraints, check UUID/sequence behavior and media references, run concurrent receipt tests, and practice point-in-time or equivalent restore. Keep SQLite backup untouched until reconciliation is complete. Application queries use `transaction.atomic()` and `select_for_update()` for receipt recording; production behavior still needs concurrency testing on PostgreSQL.

## 6. Frontend lint and test results

| Check | Result |
|---|---|
| ESLint setup review | ESLint 10, `@eslint/js` 10, React Hooks/Refresh plugins, `globals`, flat `eslint.config.js`; no unrelated lint package upgrades. |
| `npm run lint` | **Blocked:** shell reports `eslint` is not recognized because the binary is absent; offline dependency restore requires uncached `zod-validation-error@4.0.2`. Lint diagnostics are unknown. |
| `npm run build` | **Passed:** Vite 8.3.8 transformed 38 modules and emitted a production bundle. |
| Browser UI checks | Not run. |

## 7. Backend regression test results

`python manage.py test --verbosity 1` passed **39 tests in 56.6 seconds**. Coverage includes authentication/registration/logout, tenant and employee/lead workflows, finance, current subscription, mocked monthly/yearly checkout verification, price hiding/checkout disable, migration/config checks, feature gating, and Enterprise inquiry validation/idempotency/email-failure retention/admin access/approved quote/payment-before-registration. Provider calls and SMTP were mocked; no live payments or mail were sent. Existing tests do not constitute complete workflow coverage for absent documents or outbound communications.

`python manage.py check` passed. `python manage.py makemigrations --check --dry-run` reported no model drift. `git diff --check` passed after the final cleanup; Git reports expected LF-to-CRLF working-copy notices.

## 8. Security findings

- Enterprise inquiry list/detail access is available through staff-only Django Admin; the public endpoint only accepts POST. API responses do not expose the admin email. Checkout access uses a random 48-hour token stored as a hash; Razorpay secret remains backend-only.
- Public inquiries are throttled and deduplicated. Rate limiting depends on shared cache in a multi-worker deployment. SMTP retries are manual; a provider that accepts a message then times out can make delivery ambiguous.
- Active-plan role/lead/employee enforcement happens server-side. No-active subscription writes remain a known bypass pending the owner policy. Existing features without a clear plan mapping remain unenforced.
- Tenant filters/serializer validation protect normal APIs, but direct ORM/admin data entry can bypass cross-tenant relationship invariants not represented by database constraints.
- Set explicit production secret, `DEBUG`, host/origin, HTTPS, HSTS, CORS, and token-storage policies before exposure.

## 9. Files modified

- **Backend settings and environment:** `backend/aron_fincrm/aron_fincrm/settings.py`, `.env.example`, `requirements.txt`.
- **Subscription and Enterprise:** `subscriptions/models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `entitlements.py`, `enterprise_workflow.py`, `tests.py`, `README.md`, `management/commands/seed_plans.py`, and new `migrations/0007_enterprise_inquiry_review_and_checkout.py`.
- **Prior audit fixes and regression coverage:** `accounts/{tests.py,urls.py,views.py}`, `applications/{tests.py,views.py}`, `communications/tests.py`, `customers/{serializers.py,tests.py}`, `employes/{serializers.py,tests.py,views.py}`, `finance/{models.py,serializers.py,tests.py,views.py}`, `leads/{serializers.py,tests.py,views.py}`, `organizations/{date_filters.py,dates.py,serializers.py,tenant.py,tests.py,views.py}`, `permitions/{serializers.py,tests.py,views.py}`, `tasks/{analytics.py,models.py,urls.py,views.py}`.
- **Frontend:** `frientend/fincrm/package.json`, `package-lock.json`, `src/App.jsx`, `src/api.js`, `src/components/AppShell.jsx`, `PlanCatalog.jsx`, `PlanCatalog.css`, `SettingsPage.jsx`, and new `EnterpriseCheckoutPage.jsx`.
- **Audit documents:** `docs/FINCRM_AUDIT_REPORT.md` and `docs/FINCRM_AUDIT_PLAN_2026-11-22.md`.

No existing migration was rewritten or removed. No checked-in database rows were changed.

## 10. Deployment recommendations and owner decisions

1. **Send approved INR monthly/yearly prices for Starter, Growth, and Professional.** Checkout remains off until all six database values are reviewed.
2. **Choose behavior for no subscription, past due, cancelled, and expired tenants:** deny writes, read-only, free tier, or a grace period. If grace applies, specify duration and behavior for cancellation; current cancellation is immediate.
3. Review the tag/legacy-AI/plan migrations against each target database and use the clone/backup procedure above.
4. Rehearse PostgreSQL provisioning, migration, import, concurrency, backup, and restore; then apply `subscriptions.0007` and pending blacklist migrations through the deployment migration process.
5. Restore frontend npm dependencies from a networked package environment and run lint. Perform browser/staging tests for inquiry, both emails, approved Enterprise payment, registration, and failure/retry behavior using Razorpay Test Mode.
6. Add webhook-backed recurring billing or describe the product as fixed-duration, manually renewed subscriptions. Configure monitoring, shared throttling cache, and production security settings.

Until items 1–4 are resolved and staging deployment checks pass, this application is not production-ready.
