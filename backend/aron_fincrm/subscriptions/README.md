# Plans, checkout, Enterprise inquiries, and registration

The public catalog is backed by `subscriptions.Plan`. Starter, Growth, and Professional have monthly and yearly database fields, but the committed INR 1/2/3 values are placeholders. Checkout is disabled by default and the public API masks these values until actual prices are approved and stored. Enterprise is custom priced and can only use an administrator-approved quote.

## Configuration

Set secrets only in the backend environment or a secret manager. `.env.example` contains placeholders, not credentials.

```dotenv
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_secret
RAZORPAY_WEBHOOK_SECRET=your_test_webhook_secret
EMAIL_HOST_USER=yourcrm@gmail.com
EMAIL_HOST_PASSWORD=your_16_character_app_password
DEFAULT_FROM_EMAIL=yourcrm@gmail.com
ENTERPRISE_INQUIRY_ADMIN_EMAIL=yourcrm@gmail.com
FRONTEND_URL=https://app.example.com
SUBSCRIPTION_CHECKOUT_ENABLED=false
```

`SUBSCRIPTION_CHECKOUT_ENABLED` must remain false until approved prices have been written to all three paid plan rows. Turning on the flag does not change prices. Razorpay credentials and payment amounts stay on the backend.

## Paid Starter, Growth, and Professional plans

1. The public plan page loads names, limits, features, and only confirmed prices from the plan API.
2. Django reads the selected price from the database and creates a Razorpay order in paise.
3. Payment activation requires a valid checkout signature and a provider fetch confirming the order, captured status, amount, and currency.
4. A verified purchase sends a one-time registration link that expires after 48 hours. Registration creates the organization, active subscription, and payment record in one transaction.

The public plans use one-time Razorpay Orders. Their checkout stays disabled until the catalog prices are confirmed. Enterprise has no public automatic checkout.

## Enterprise inquiry and conversion

`POST /api/v1/subscriptions/enterprise-inquiry/` validates and saves an inquiry with status `New`. It attempts exactly two notifications: one to the customer and one to `ENTERPRISE_INQUIRY_ADMIN_EMAIL`. Failed sends do not delete the inquiry; staff can retry missing notifications from Django Admin. An idempotency key and short duplicate window prevent repeated form submissions from creating duplicate inquiries or email notifications. Public inquiries never create payment or registration links.

Only FinCRM superusers can use **Enterprise inquiries** in the signed-in admin dashboard or Django Admin. The dashboard supports search, status/notes management, creation of an inquiry-specific plan, and manual payment invitation after approval. A plan can use a one-time Order or a Razorpay recurring Plan and Subscription. Enterprise invitations are token-protected and expire after 48 hours; registration invitations are one-time and expire after 24 hours. Submitting an inquiry never creates payment, login, or registration links.

Enterprise payment access is granted from signed webhooks, not a browser callback. Configure the Razorpay Test Mode webhook URL as `/api/v1/subscriptions/webhooks/razorpay/`, use the separate `RAZORPAY_WEBHOOK_SECRET`, and enable the needed payment and subscription events (`payment.captured`, `payment.failed`, `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`). Webhook event IDs and provider payment IDs are deduplicated. A confirmed Enterprise payment/authorization sends the secure registration email; a notification failure keeps the saved checkout eligible for provider retry.

Recurring Enterprise subscriptions are associated with the organization after the registration token is redeemed. Captured recurring payments are linked to the local subscription, and lifecycle/failure webhooks update its status and next billing date. Cancellation of a provider-backed subscription is sent to Razorpay before the local subscription is marked cancelled. `/subscriptions/subscribe/` remains disabled (410); standard paid-plan checkout remains one-time and keeps its existing signature plus provider-fetch verification.

The endpoint is throttled to 10 submissions per hour per client IP. Production should use a shared cache for consistent limits across application workers.

## Migration precautions

Do not run migration or plan-seeding commands against an existing deployment without a current backup, a staging rehearsal, and a review of the project's data-sensitive migration history. In particular, migration `0005` drops legacy AI tables and `0006` upserts plan catalog values. Migrations `0007`–`0014` extend existing subscription tables, add the webhook event ledger and uniqueness constraint, and expand inquiry statuses; review and apply them through the deployment's migration procedure. No existing fields or tables are removed by these new migrations.

`seed_plans` now creates missing plans without overwriting existing plan fields; it still creates placeholder prices on a new database. Correct and verify the catalog before enabling checkout.
