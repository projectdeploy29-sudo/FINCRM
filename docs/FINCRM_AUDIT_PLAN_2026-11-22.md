# FinCRM audit and repair plan — 2026-11-22

## Baseline

- The checkout was clean before audit work and is on `codex/fincrm-complete-audit-2026-11-22`.
- Phase 1 was read-only. No production payment was attempted, no seed command was run, and no migration was applied to the checked-in SQLite database.
- Baseline checks: `manage.py check` passed; migration consistency failed because `Plan.daily_ai_tokens` exists in migration history but not in the model; the backend test suite had three failures that assert superseded registration, plan ordering, and manual subscription behavior; the frontend build passed; lint could not start because the ESLint executable is unavailable.

## Planned changes

1. Restore the `Plan.daily_ai_tokens` model field to match the already-applied migration state. Do not remove the column or create a data-deleting migration.
2. Make `Organization.is_active` read-only in the self-service organization serializer so an organization administrator cannot disable their own tenant through that endpoint. Treat expired subscriptions as inactive in the current-subscription API and reject receipts for waived or cancelled schedules.
3. Complete `Team` assignment validation for the legacy employee team-leader relation, checking that the employee is active and belongs to the selected department and tenant.
4. Harden frontend API pagination so an API-provided `next` URL must remain on the configured API origin and path before an Authorization header is sent. Correct refresh-token persistence/state synchronization and add refresh-token revocation on logout, with a short access-token lifetime.
5. Apply date filters for datetime fields using the organization's timezone and half-open UTC bounds. Keep date-only fields inclusive.
6. Reduce the pipeline endpoint's per-lead database work with batched related data and counts while preserving the response shape.
7. Surface existing, implemented frontend modules in navigation according to their configured minimum role levels: role management, message drafts, subscription, billing, and hierarchy.
8. Remove only imports confirmed unused by a repository-wide reference check, the unreferenced customer-tag serializer, and the disabled manual subscription serializer. Remove React type-only packages after confirming the frontend has no TypeScript files or configuration. Retain utility candidates whose purpose may be indirect or externally referenced.
9. Update stale tests to reflect paid-checkout registration and disabled manual subscription activation, and add focused regression coverage for the changes above.
10. Replace the stale audit report with a current report that records findings, modifications, test results, and unresolved release risks.

## Explicitly out of scope for this repair pass

- Do not delete or rewrite existing migrations, including the applied subscription migration that drops legacy AI tables and edits `django_migrations`.
- Do not run `migrate`, reset or edit the working database, run destructive seed commands, or make real payment transactions.
- Do not invent production plan prices. The seeded INR 1/2/3 monthly/yearly values need confirmation before live checkout is enabled.
- Do not claim that document storage, payment-proof upload, outbound email/SMS/WhatsApp delivery, recurring billing, or Razorpay webhooks work; the corresponding integrations are incomplete or absent.

