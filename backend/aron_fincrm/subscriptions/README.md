# Plans, Razorpay, and organization registration

The public plan catalog is backed by `subscriptions.Plan`. Monthly and yearly prices for Starter, Growth, and Professional are seeded as six purchasable price options; Enterprise has custom pricing and no checkout price.

## Configuration

Put these settings in `backend/aron_fincrm/.env` and restart Django:

```dotenv
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_secret
EMAIL_HOST_USER=yourcrm@gmail.com
EMAIL_HOST_PASSWORD=your_16_character_app_password
FRONTEND_URL=http://localhost:5173
```

Gmail uses `smtp.gmail.com`, port 587, and TLS by default. The payment secret stays on the backend. Do not put it in frontend variables.

## New organization purchase

1. The plan page loads plan names, limits, features, and prices from the public plan API.
2. The buyer selects a billing cycle, confirms a plan, and enters the email for the registration link.
3. Django reads the selected price from the database and creates a Razorpay order in paise.
4. After Checkout returns, Django checks the payment signature and fetches the payment from Razorpay. It only accepts the payment after Razorpay reports the expected order, amount, currency, and captured status.
5. Django emails a link containing a random token. Only the token hash is stored; the link expires after 48 hours and can create one organization/admin account.
6. Registration creates the organization, active subscription, and payment record in one database transaction.

The API endpoints are `POST /api/v1/subscriptions/checkout/create/`, `POST /api/v1/subscriptions/checkout/verify/`, and `POST /api/v1/organizations/register/`. Direct subscription activation through the old `/subscriptions/subscribe/` endpoint is disabled.

## Enterprise

`POST /api/v1/subscriptions/enterprise-inquiry/` stores the submitted inquiry, emails a confirmation to the customer, and sends the full inquiry to `EMAIL_HOST_USER`.

Apply migrations and refresh the plan catalog with:

```powershell
python manage.py migrate
python manage.py seed_plans
```
