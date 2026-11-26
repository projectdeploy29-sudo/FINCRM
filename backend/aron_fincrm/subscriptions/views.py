import uuid
import hashlib
import json
from datetime import timedelta
import hmac
from io import BytesIO
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.http import FileResponse
from django.utils import timezone
from django.utils.html import escape
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.permissions import IsAuthenticated
from subscriptions.models import AIAssistantUsage, EnterpriseInquiry, Plan, Subscription, Payment, PlanCheckout, SubscriptionPlatformSettings
from subscriptions.configuration import is_subscription_checkout_enabled
from subscriptions.serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    PaymentSerializer,
    PlanCheckoutSerializer,
    PlanCheckoutVerificationSerializer,
    EnterpriseInquirySerializer,
    EnterpriseInquiryAdminSerializer,
    EnterprisePlanCreationSerializer,
    EnterprisePlanAdminSerializer,
    EnterprisePlanUpdateSerializer,
    SubscriptionPlanAdminSerializer,
    InvoiceIssuerSettingsSerializer,
    PaymentInvoiceDetailsSerializer,
)
from accounts.models import Manager, TeamLead
from employes.models import Employee
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin
from subscriptions.registration import (
    REGISTRATION_LINK_LIFETIME,
    RegistrationEmailError,
    create_registration_token,
    hash_registration_token,
    send_registration_link,
)
from subscriptions.razorpay import (
    RazorpayConfigurationError,
    RazorpayProviderError,
    create_order as create_razorpay_order,
    fetch_payment as fetch_razorpay_payment,
    valid_checkout_signature,
    valid_webhook_signature,
    create_plan as create_razorpay_plan,
    create_subscription as create_razorpay_subscription,
    cancel_subscription as cancel_razorpay_subscription,
)
from subscriptions.enterprise_workflow import send_inquiry_notifications
from subscriptions.registration import hash_registration_token
from subscriptions.webhooks import process_razorpay_event, WebhookProcessingError
from rest_framework.permissions import BasePermission
from subscriptions.models import RazorpayWebhookEvent
from subscriptions.payment_documents import build_payment_receipt, build_test_gst_invoice


class PlanListView(generics.ListAPIView):
    """
    GET /api/v1/subscriptions/plans/
    Lists all available SaaS subscription tiers and features.
    """
    queryset = Plan.objects.filter(is_active=True).annotate(
        custom_plan_sort=Case(
            When(monthly_price__isnull=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by('custom_plan_sort', 'monthly_price', 'name')
    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    pagination_class = None


class PlanCheckoutCreateView(APIView):
    """Create a Razorpay order from the selected database plan and billing cycle."""
    permission_classes = [AllowAny]

    def post(self, request):
        if not is_subscription_checkout_enabled():
            return Response(
                {'detail': 'Plan checkout is disabled until the catalog prices are confirmed.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = PlanCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        plan = Plan.objects.filter(id=values['plan_id'], is_active=True).first()
        if not plan:
            return Response({'detail': 'Choose an active plan.'}, status=status.HTTP_400_BAD_REQUEST)
        if plan.code == 'enterprise':
            return Response({'detail': 'Enterprise requires an approved custom quote. Submit an inquiry first.'}, status=status.HTTP_400_BAD_REQUEST)

        if not plan.prices_confirmed:
            return Response({'detail': 'This plan is not available for checkout until its prices are confirmed.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cycle = values['billing_cycle']
        amount = plan.monthly_price if cycle == Subscription.BillingCycle.MONTHLY else plan.yearly_price
        if amount is None or amount <= 0:
            return Response({'detail': 'This plan uses custom pricing. Submit the enterprise inquiry form.'}, status=status.HTTP_400_BAD_REQUEST)

        organization = None
        if request.user and request.user.is_authenticated:
            if not request.user.is_active:
                return Response({'detail': 'Active accounts are required to purchase a plan.'}, status=status.HTTP_403_FORBIDDEN)
            role = get_user_role_context(request.user, request)
            if role['hierarchy_level'] < 90:
                return Response({'detail': 'Only an organization admin can purchase a plan for an existing organization.'}, status=status.HTTP_403_FORBIDDEN)
            organization = get_user_organization(request.user, request)
            if not organization or not organization.is_active:
                return Response({'detail': 'No organization is associated with this account.'}, status=status.HTTP_400_BAD_REQUEST)

        email = (values.get('email') or getattr(request.user, 'email', '') or '').strip().lower()
        if not email:
            return Response({'email': ['Enter an email address for the registration link.']}, status=status.HTTP_400_BAD_REQUEST)

        checkout = PlanCheckout.objects.create(
            plan=plan,
            organization=organization,
            billing_cycle=cycle,
            purchaser_email=email,
            amount=amount,
            currency='INR',
            status=PlanCheckout.Status.CREATING,
        )
        try:
            key_id, razorpay_order = create_razorpay_order(checkout)
        except RazorpayConfigurationError:
            checkout.status = PlanCheckout.Status.FAILED
            checkout.save(update_fields=['status'])
            return Response({'detail': 'Razorpay is not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to the backend .env file.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (RazorpayProviderError, ImportError):
            checkout.status = PlanCheckout.Status.FAILED
            checkout.save(update_fields=['status'])
            return Response({'detail': 'Razorpay could not create the payment order. Check provider availability and try again.'}, status=status.HTTP_502_BAD_GATEWAY)

        checkout.razorpay_order_id = razorpay_order['id']
        checkout.status = PlanCheckout.Status.PENDING
        checkout.save(update_fields=['razorpay_order_id', 'status'])
        return Response({
            'key_id': key_id,
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'plan_name': plan.name,
            'billing_cycle': cycle,
            'email': email,
        }, status=status.HTTP_201_CREATED)


class PlanCheckoutVerifyView(APIView):
    """Verify Checkout signature and captured payment before activation or registration."""
    permission_classes = [AllowAny]

    def post(self, request):
        # Enterprise checkout status is exclusively driven by signed Razorpay webhooks.
        # Never let the browser callback grant access or start registration.
        incoming_order_id = request.data.get('razorpay_order_id')
        enterprise_checkout = PlanCheckout.objects.filter(
            razorpay_order_id=incoming_order_id,
            enterprise_inquiry__isnull=False,
        ).first() if incoming_order_id else None
        if enterprise_checkout:
            return Response({
                'detail': 'Payment is being confirmed securely. Registration is emailed after Razorpay confirms the payment.',
                'status': enterprise_checkout.status,
            }, status=status.HTTP_202_ACCEPTED)
        serializer = PlanCheckoutVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        checkout = PlanCheckout.objects.select_related('plan', 'organization', 'enterprise_inquiry').filter(
            razorpay_order_id=values['razorpay_order_id'],
        ).first()
        if not checkout:
            return Response({'detail': 'Checkout order was not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            signature_valid = valid_checkout_signature(
                checkout.razorpay_order_id,
                values['razorpay_payment_id'],
                values['razorpay_signature'],
            )
        except RazorpayConfigurationError:
            return Response({'detail': 'Razorpay is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not signature_valid:
            return Response({'detail': 'Razorpay payment signature is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        if checkout.razorpay_payment_id == values['razorpay_payment_id'] and checkout.status in (
            PlanCheckout.Status.PAID,
            PlanCheckout.Status.ACTIVATED,
            PlanCheckout.Status.COMPLETED,
        ):
            return Response({'detail': self._success_message(checkout), 'status': checkout.status}, status=status.HTTP_200_OK)
        if checkout.status != PlanCheckout.Status.PENDING:
            return Response({'detail': 'This checkout is no longer awaiting payment.'}, status=status.HTTP_409_CONFLICT)
        if checkout.enterprise_inquiry_id and not EnterpriseCheckoutDetailsView.is_currently_approved(checkout):
            return Response({'detail': 'This Enterprise quote is no longer approved for payment.'}, status=status.HTTP_409_CONFLICT)

        try:
            provider_payment = fetch_razorpay_payment(values['razorpay_payment_id'])
        except RazorpayConfigurationError:
            return Response({'detail': 'Razorpay is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (RazorpayProviderError, ImportError):
            return Response({'detail': 'Razorpay payment status could not be checked. Try again shortly.'}, status=status.HTTP_502_BAD_GATEWAY)

        if (
            provider_payment.get('order_id') != checkout.razorpay_order_id
            or provider_payment.get('status') != 'captured'
            or provider_payment.get('amount') != int(checkout.amount * 100)
            or provider_payment.get('currency') != checkout.currency
        ):
            return Response({'detail': 'Payment is not captured for the expected order amount.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                claim_query = PlanCheckout.objects.filter(
                    pk=checkout.pk,
                    status=PlanCheckout.Status.PENDING,
                )
                if checkout.enterprise_inquiry_id:
                    inquiry = checkout.enterprise_inquiry
                    claim_query = claim_query.filter(
                        enterprise_inquiry__status=EnterpriseInquiry.Status.PAYMENT_INITIATED,
                        amount=inquiry.agreed_amount,
                        billing_cycle=inquiry.billing_cycle,
                        purchaser_email__iexact=inquiry.email,
                        organization_id=inquiry.organization_id,
                    )
                claimed = claim_query.update(status=PlanCheckout.Status.PROCESSING)
                if claimed != 1:
                    checkout.refresh_from_db()
                    if (
                        checkout.razorpay_payment_id == values['razorpay_payment_id']
                        and checkout.status in (PlanCheckout.Status.PAID, PlanCheckout.Status.ACTIVATED, PlanCheckout.Status.COMPLETED)
                    ):
                        return Response({'detail': self._success_message(checkout), 'status': checkout.status}, status=status.HTTP_200_OK)
                    return Response({'detail': 'This checkout has already been processed.'}, status=status.HTTP_409_CONFLICT)
                checkout = PlanCheckout.objects.select_related('plan', 'organization').get(pk=checkout.pk)

                now = timezone.now()
                checkout.razorpay_payment_id = values['razorpay_payment_id']
                checkout.paid_at = now
                if checkout.organization_id:
                    self._activate_organization_subscription(checkout, now)
                    checkout.status = PlanCheckout.Status.ACTIVATED
                    if checkout.enterprise_inquiry_id:
                        EnterpriseInquiry.objects.filter(pk=checkout.enterprise_inquiry_id).update(
                            status=EnterpriseInquiry.Status.COMPLETED,
                        )
                else:
                    token = create_registration_token()
                    checkout.status = PlanCheckout.Status.PAID
                    checkout.registration_token_hash = hash_registration_token(token)
                    checkout.registration_token_expires_at = now + REGISTRATION_LINK_LIFETIME
                    checkout.registration_email_sent_at = send_registration_link(checkout, token)
                checkout.save(update_fields=[
                    'razorpay_payment_id',
                    'paid_at',
                    'status',
                    'registration_token_hash',
                    'registration_token_expires_at',
                    'registration_email_sent_at',
                ])
        except RegistrationEmailError:
            return Response({'detail': 'Payment is captured, but the email could not be sent. Check SMTP settings and retry payment confirmation.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'detail': self._success_message(checkout), 'status': checkout.status}, status=status.HTTP_200_OK)

    @staticmethod
    def _success_message(checkout):
        if checkout.organization_id:
            return 'Payment verified and the organization subscription is active.'
        if checkout.status == PlanCheckout.Status.COMPLETED:
            return 'Payment and organization registration are complete.'
        return 'Payment verified. A one-time registration link has been sent to your email.'

    @staticmethod
    def _activate_organization_subscription(checkout, now):
        duration = timedelta(days=30) if checkout.billing_cycle == Subscription.BillingCycle.MONTHLY else timedelta(days=365)
        end_date = now + duration
        Subscription.objects.filter(
            organization=checkout.organization,
            status__in=(Subscription.Status.ACTIVE, Subscription.Status.TRIALING),
        ).update(status=Subscription.Status.CANCELLED, cancelled_at=now)
        subscription = Subscription.objects.create(
            organization=checkout.organization,
            plan=checkout.plan,
            Subscriptioncode='SUB-' + uuid.uuid4().hex[:12].upper(),
            billing_cycle=checkout.billing_cycle,
            status=Subscription.Status.ACTIVE,
            start_date=now,
            end_date=end_date,
            next_billing_date=end_date.date(),
        )
        payment = Payment.objects.create(
            subscription=subscription,
            checkout=checkout,
            amount=checkout.amount,
            currency=checkout.currency,
            provider='RAZORPAY',
            provider_payment_id=checkout.razorpay_payment_id,
            invoice_reference='INV-' + subscription.Subscriptioncode,
            status=Payment.Status.SUCCEEDED,
            paid_at=now,
        )
        subscription.payment = payment
        subscription.save(update_fields=['payment'])


class SubscriptionCurrentView(APIView):
    """
    GET /api/v1/subscriptions/current/
    Returns the organization's current active subscription, plan tier, and resource usage.
    """
    permission_classes = [IsAuthenticatedTenant]

    def get(self, request):
        org = get_user_organization(request.user)
        if not org:
            return Response({"detail": "No organization associated."}, status=status.HTTP_404_NOT_FOUND)

        sub = Subscription.objects.filter(
            organization=org,
            status__in=['active', 'trialing'],
            end_date__gt=timezone.now(),
        ).select_related('plan').order_by('-created_at').first()

        if not sub:
            return Response(
                {"detail": "No active subscription found for this organization.", "has_active_subscription": False},
                status=status.HTTP_200_OK,
            )

        serializer = SubscriptionSerializer(sub)
        data = serializer.data
        data['has_active_subscription'] = True
        role = get_user_role_context(request.user, request)
        if role['hierarchy_level'] >= 90 and role['role_code'] != 'lead_portal':
            today = timezone.localdate()
            token_usage = AIAssistantUsage.objects.filter(
                organization=org,
                created_at__date=today,
            ).aggregate(
                input_tokens=Sum('input_tokens'),
                output_tokens=Sum('output_tokens'),
                total_tokens=Sum('total_tokens'),
            )
            total_limit = sub.plan.daily_ai_tokens
            tokens_used = token_usage['total_tokens'] or 0
            data['ai_tokens'] = {
                'period': 'today',
                'used': tokens_used,
                'total': total_limit,
                'remaining': max(total_limit - tokens_used, 0) if total_limit is not None else None,
                'input_used': token_usage['input_tokens'] or 0,
                'output_used': token_usage['output_tokens'] or 0,
            }
        return Response(data, status=status.HTTP_200_OK)


class SubscribeView(APIView):
    """
    POST /api/v1/subscriptions/subscribe/
    Allows an Org Admin to subscribe or upgrade their organization to a plan.
    """
    permission_classes = [IsAuthenticatedTenant, IsOrgAdmin]

    def post(self, request):
        return Response(
            {'detail': 'Direct subscription activation is disabled. Create and verify a Razorpay checkout order.'},
            status=status.HTTP_410_GONE,
        )


class EnterpriseInquiryView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'enterprise_inquiry'

    @staticmethod
    def _identity_match(queryset, values):
        return queryset.filter(
            email__iexact=values['email'].strip(),
            phone=values['phone'].strip(),
            organization_name__iexact=values['organization_name'].strip(),
        )

    @staticmethod
    def _same_submission(inquiry, values):
        return all(
            getattr(inquiry, field) == (values.get(field, '') or '')
            for field in ('full_name', 'phone', 'organization_name', 'website', 'linkedin_url', 'note')
        ) and inquiry.email.casefold() == values['email'].casefold()

    def post(self, request):
        serializer = EnterpriseInquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        # A honeypot hit gets a normal-looking success response but is never stored or emailed.
        if values.get('fax', '').strip():
            return Response({'detail': 'Your inquiry was received. We will contact you soon.'}, status=status.HTTP_201_CREATED)

        raw_key = request.headers.get('Idempotency-Key', '').strip()
        try:
            idempotency_key = uuid.UUID(raw_key) if raw_key else None
        except ValueError:
            return Response({'detail': 'Idempotency-Key must be a UUID.'}, status=status.HTTP_400_BAD_REQUEST)

        duplicate = None
        if idempotency_key:
            duplicate = EnterpriseInquiry.objects.filter(idempotency_key=idempotency_key).first()
            if duplicate and not self._same_submission(duplicate, values):
                return Response({'detail': 'This request key was already used for different inquiry details.'}, status=status.HTTP_409_CONFLICT)
        if duplicate is None:
            recent = self._identity_match(
                EnterpriseInquiry.objects.filter(created_at__gte=timezone.now() - timedelta(minutes=15)),
                values,
            ).order_by('-created_at').first()
            if recent:
                duplicate = recent

        if duplicate:
            return Response(
                {'detail': 'Your inquiry was received. We will contact you soon.'},
                status=status.HTTP_200_OK,
            )

        try:
            with transaction.atomic():
                inquiry = serializer.save(idempotency_key=idempotency_key)
        except IntegrityError:
            if not idempotency_key:
                raise
            inquiry = EnterpriseInquiry.objects.filter(idempotency_key=idempotency_key).first()
            if not inquiry or not self._same_submission(inquiry, values):
                return Response({'detail': 'This request key was already used for different inquiry details.'}, status=status.HTTP_409_CONFLICT)
            return Response(
                {'detail': 'Your inquiry was received. We will contact you soon.'},
                status=status.HTTP_200_OK,
            )
        notifications_sent = send_inquiry_notifications(inquiry, only_unsent=False)
        response = {'detail': 'Your inquiry was received. We will contact you soon.'}
        if not notifications_sent:
            # The record is kept; retries with the same idempotency key will not create or re-email it.
            response['detail'] = 'Your inquiry was saved. Confirmation email delivery may be delayed; our team has the inquiry.'
            response['email_delivery'] = 'pending administrator review'
        return Response(response, status=status.HTTP_201_CREATED)


class EnterpriseCheckoutDetailsView(APIView):
    permission_classes = [AllowAny]

    @staticmethod
    def is_currently_approved(checkout):
        inquiry = checkout.enterprise_inquiry
        legacy_approved = bool(
            inquiry
            and inquiry.status == EnterpriseInquiry.Status.PAYMENT_INITIATED
            and checkout.amount == inquiry.agreed_amount
            and checkout.billing_cycle == inquiry.billing_cycle
            and checkout.purchaser_email.casefold() == inquiry.email.casefold()
            and checkout.organization_id == inquiry.organization_id
        )
        admin_approved = bool(
            inquiry
            and inquiry.custom_plan_id == checkout.plan_id
            and inquiry.status in {
                EnterpriseInquiry.Status.PLAN_CREATED,
                EnterpriseInquiry.Status.PAYMENT_PENDING,
                EnterpriseInquiry.Status.CONVERTED,
                EnterpriseInquiry.Status.COMPLETED,
            }
        )
        return legacy_approved or admin_approved

    def get(self, request, checkout_id=None):
        token = request.query_params.get('token', '')
        if not token:
            return Response({'detail': 'Checkout link is invalid or expired.'}, status=status.HTTP_404_NOT_FOUND)
        checkout_query = PlanCheckout.objects.select_related('plan', 'enterprise_inquiry', 'organization').filter(
            enterprise_inquiry__isnull=False,
            enterprise_access_token_expires_at__gt=timezone.now(),
        )
        if checkout_id:
            checkout_query = checkout_query.filter(pk=checkout_id)
        else:
            checkout_query = checkout_query.filter(enterprise_access_token_hash=hash_registration_token(token))
        checkout = checkout_query.first()
        if (
            not checkout
            or not self.is_currently_approved(checkout)
            or not hmac.compare_digest(
                checkout.enterprise_access_token_hash,
                hash_registration_token(token),
            )
        ):
            return Response({'detail': 'Checkout link is invalid or expired.'}, status=status.HTTP_404_NOT_FOUND)
        if checkout.status in {PlanCheckout.Status.PAID, PlanCheckout.Status.COMPLETED, PlanCheckout.Status.ACTIVATED}:
            return Response({'status': checkout.status, 'payment_mode': checkout.payment_mode})
        if checkout.status not in {PlanCheckout.Status.PENDING, PlanCheckout.Status.PENDING_AUTHORIZATION}:
            return Response({'detail': 'This checkout is no longer available.'}, status=status.HTTP_410_GONE)
        if not settings.RAZORPAY_KEY_ID or (checkout.payment_mode == 'one_time' and not checkout.razorpay_order_id) or (checkout.payment_mode == 'recurring' and not checkout.razorpay_subscription_id):
            return Response({'detail': 'Checkout is temporarily unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        response = Response({
            'key_id': settings.RAZORPAY_KEY_ID,
            'status': checkout.status,
            'order_id': checkout.razorpay_order_id,
            'subscription_id': checkout.razorpay_subscription_id,
            'payment_mode': checkout.payment_mode,
            'amount': int(checkout.amount * 100),
            'currency': checkout.currency,
            'plan_name': checkout.plan.name,
            'billing_cycle': checkout.billing_cycle,
            'email': checkout.purchaser_email,
            'plan_snapshot': checkout.plan_snapshot,
        })
        response['Cache-Control'] = 'no-store'
        return response


class RegistrationInvitationDetailsView(APIView):
    """Reveal only prefill data to the holder of an active one-time registration token."""
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token', '')
        if not token:
            return Response({'detail': 'Registration link is invalid or expired.'}, status=status.HTTP_404_NOT_FOUND)
        checkout = PlanCheckout.objects.select_related('enterprise_inquiry', 'organization').filter(
            registration_token_hash=hash_registration_token(token),
            status=PlanCheckout.Status.PAID,
            registration_token_used_at__isnull=True,
            registration_token_expires_at__gt=timezone.now(),
        ).first()
        if not checkout:
            return Response({'detail': 'Registration link is invalid or expired.'}, status=status.HTTP_404_NOT_FOUND)
        inquiry = checkout.enterprise_inquiry
        customer_name = checkout.customer_name or (inquiry.full_name if inquiry else '')
        name_parts = customer_name.split(maxsplit=1)
        response = Response({
            'email': checkout.purchaser_email,
            'organization_name': (checkout.organization.name if checkout.organization_id else inquiry.organization_name) if inquiry else '',
            'first_name': name_parts[0] if name_parts else '',
            'last_name': name_parts[1] if len(name_parts) > 1 else '',
            'enterprise': inquiry is not None,
            'plan_name': checkout.plan.name,
        })
        response['Cache-Control'] = 'no-store'
        return response


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticatedTenant, IsOrgAdmin]
    def post(self,request):
        org=get_user_organization(request.user,request)
        sub=Subscription.objects.filter(
            organization=org,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.TRIALING, Subscription.Status.PAST_DUE, Subscription.Status.HALTED],
        ).order_by('-created_at').first()
        if not sub:return Response({'detail':'There is no active subscription to cancel.'},status=400)
        if sub.razorpay_subscription_id:
            try:
                provider_subscription = cancel_razorpay_subscription(sub.razorpay_subscription_id)
            except RazorpayConfigurationError:
                return Response({'detail': 'Razorpay is not configured. The subscription remains active.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except (RazorpayProviderError, ImportError):
                return Response({'detail': 'Razorpay could not confirm cancellation. The subscription remains active.'}, status=status.HTTP_502_BAD_GATEWAY)
            if provider_subscription.get('status') != 'cancelled':
                return Response({'detail': 'Razorpay has not confirmed cancellation; the subscription remains active.'}, status=status.HTTP_502_BAD_GATEWAY)
        sub.status=Subscription.Status.CANCELLED; sub.cancelled_at=timezone.now(); sub.save(update_fields=['status','cancelled_at'])
        return Response(SubscriptionSerializer(sub).data)


class PaymentHistoryView(generics.ListAPIView):
    """
    GET /api/v1/subscriptions/payments/
    Lists billing invoice payment records for the organization.
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticatedTenant, IsOrgAdmin]

    def get_queryset(self):
        org = get_user_organization(self.request.user)
        if not org:
            return Payment.objects.none()
        return Payment.objects.filter(subscription__organization=org).select_related(
            'subscription__plan', 'subscription__organization', 'checkout__plan',
        ).order_by('-created_at')


class PaymentDocumentDownloadView(APIView):
    """Download a paid receipt or clearly marked GST invoice test draft."""
    permission_classes = [IsAuthenticatedTenant, IsOrgAdmin]

    def get(self, request, payment_id, document_type):
        org = get_user_organization(request.user, request)
        if not org:
            return Response({'detail': 'No organization is associated with this account.'}, status=status.HTTP_404_NOT_FOUND)
        payment = Payment.objects.filter(
            pk=payment_id,
            subscription__organization=org,
            status=Payment.Status.SUCCEEDED,
        ).select_related(
            'subscription__plan', 'subscription__organization', 'checkout__plan', 'checkout__organization',
        ).first()
        if not payment:
            return Response({'detail': 'Paid billing document was not found.'}, status=status.HTTP_404_NOT_FOUND)
        if document_type == 'receipt':
            reference, content = build_payment_receipt(payment=payment)
            filename = f'auron-fin-crm-payment-receipt-{reference}.pdf'
        elif document_type == 'invoice':
            reference, content = build_test_gst_invoice(payment=payment)
            filename = f'auron-fin-crm-gst-test-draft-{reference}.pdf'
        else:
            return Response({'detail': 'Unknown billing document.'}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(BytesIO(content), as_attachment=True, filename=filename, content_type='application/pdf')
        response['Cache-Control'] = 'private, no-store'
        return response


class IsFinCRMAdministrator(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class SubscriptionPlanManagementView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def get(self, request):
        plans = Plan.objects.exclude(code='enterprise').order_by('created_at', 'name')
        return Response(SubscriptionPlanAdminSerializer(plans, many=True).data)

    def post(self, request):
        serializer = SubscriptionPlanAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(SubscriptionPlanAdminSerializer(plan).data, status=status.HTTP_201_CREATED)


class SubscriptionPlanDetailManagementView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def patch(self, request, plan_id):
        plan = Plan.objects.exclude(code='enterprise').filter(pk=plan_id).first()
        if not plan:
            return Response({'detail': 'Plan was not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = SubscriptionPlanAdminSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        return Response(SubscriptionPlanAdminSerializer(plan).data)


class SubscriptionCheckoutSettingsView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    @staticmethod
    def _unconfirmed_plans():
        return list(Plan.objects.filter(is_active=True).exclude(code='enterprise').filter(
            Q(prices_confirmed=False) | Q(monthly_price__isnull=True) | Q(yearly_price__isnull=True)
            | Q(monthly_price__lte=0) | Q(yearly_price__lte=0)
        ).values('id', 'name', 'code'))

    def get(self, request):
        platform_settings, _ = SubscriptionPlatformSettings.objects.get_or_create(
            pk=1, defaults={'checkout_enabled': settings.SUBSCRIPTION_CHECKOUT_ENABLED},
        )
        unconfirmed = self._unconfirmed_plans()
        return Response({
            'checkout_enabled': platform_settings.checkout_enabled,
            'can_enable': not unconfirmed,
            'unconfirmed_plans': unconfirmed,
            'updated_at': platform_settings.updated_at,
        })

    def patch(self, request):
        if not isinstance(request.data.get('checkout_enabled'), bool):
            return Response({'checkout_enabled': ['Provide true or false.']}, status=status.HTTP_400_BAD_REQUEST)
        enabled = request.data['checkout_enabled']
        if enabled:
            unconfirmed = self._unconfirmed_plans()
            if unconfirmed:
                return Response({
                    'detail': 'Checkout cannot be enabled until every active paid plan has confirmed positive monthly and yearly prices.',
                    'unconfirmed_plans': unconfirmed,
                }, status=status.HTTP_409_CONFLICT)
        platform_settings, _ = SubscriptionPlatformSettings.objects.get_or_create(pk=1)
        platform_settings.checkout_enabled = enabled
        platform_settings.updated_by = request.user
        platform_settings.save(update_fields=['checkout_enabled', 'updated_by', 'updated_at'])
        return self.get(request)


class EnterpriseManagementView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def get(self, request):
        platform_settings, _ = SubscriptionPlatformSettings.objects.get_or_create(pk=1)
        inquiries = EnterpriseInquiry.objects.select_related('assigned_admin', 'custom_plan').order_by('-created_at')
        checkouts = PlanCheckout.objects.filter(enterprise_inquiry__isnull=False).select_related('plan', 'organization').order_by('-created_at')
        customers = []
        for inquiry in inquiries.filter(status=EnterpriseInquiry.Status.COMPLETED).select_related('organization', 'custom_plan'):
            subscription = Subscription.objects.filter(organization=inquiry.organization).select_related('plan').order_by('-created_at').first() if inquiry.organization_id else None
            customers.append({
                'inquiry_id': str(inquiry.pk),
                'full_name': inquiry.full_name,
                'email': inquiry.email,
                'phone': inquiry.phone,
                'organization': inquiry.organization.name if inquiry.organization_id else inquiry.organization_name,
                'plan': subscription.plan.name if subscription else (inquiry.custom_plan.name if inquiry.custom_plan_id else ''),
                'subscription_status': subscription.status if subscription else 'pending',
                'registered': bool(subscription),
            })
        today = timezone.localdate()
        all_subscriptions = Subscription.objects.select_related(
            'plan', 'organization', 'payment__checkout__enterprise_inquiry',
        ).order_by('-created_at')
        detailed_subscriptions = []
        User = get_user_model()
        for subscription in all_subscriptions:
            organization = subscription.organization
            checkout = (
                subscription.payment.checkout
                if subscription.payment_id and subscription.payment.checkout_id else None
            )
            if checkout is None:
                checkout = PlanCheckout.objects.filter(
                    organization=organization, plan=subscription.plan,
                ).select_related('enterprise_inquiry', 'plan').order_by('-paid_at', '-created_at').first()
            purchaser = User.objects.filter(
                default_organization=organization, is_superuser=False,
            ).order_by('date_joined').first()
            purchaser_name = (
                (checkout.customer_name if checkout else '')
                or (purchaser.get_full_name() if purchaser else '')
                or (purchaser.username if purchaser else '')
                or organization.name
            )
            purchaser_email = (
                (checkout.purchaser_email if checkout else '')
                or (purchaser.email if purchaser else '')
                or organization.email
            )
            employee_count = Employee.objects.filter(organization=organization).count()
            manager_count = Manager.objects.filter(organization=organization).count()
            team_lead_count = TeamLead.objects.filter(organization=organization).count()
            staff_count = employee_count + manager_count + team_lead_count
            active_staff_count = (
                Employee.objects.filter(organization=organization, employment_status='active').count()
                + Manager.objects.filter(organization=organization, employment_status='active').count()
                + TeamLead.objects.filter(organization=organization, employment_status='active').count()
            )
            token_usage = AIAssistantUsage.objects.filter(
                organization=organization, created_at__date=today,
            ).aggregate(
                input_tokens=Sum('input_tokens'),
                output_tokens=Sum('output_tokens'),
                total_tokens=Sum('total_tokens'),
            )
            daily_token_limit = subscription.plan.daily_ai_tokens
            tokens_used = token_usage['total_tokens'] or 0
            serialized = SubscriptionSerializer(subscription).data
            serialized.update({
                'purchaser': {
                    'name': purchaser_name,
                    'email': purchaser_email,
                    'username': purchaser.username if purchaser else '',
                    'phone': organization.phone,
                    'registered_at': purchaser.date_joined if purchaser else None,
                },
                'registration_status': 'completed' if purchaser else 'admin account not found',
                'staff_accounts': {
                    'used': staff_count,
                    'limit': subscription.plan.max_employees,
                    'active': active_staff_count,
                    'employees': employee_count,
                    'managers': manager_count,
                    'team_leads': team_lead_count,
                    'remaining': max(subscription.plan.max_employees - staff_count, 0)
                    if subscription.plan.max_employees is not None else None,
                },
                'ai_tokens': {
                    'period': 'today',
                    'limit': daily_token_limit,
                    'input_used': token_usage['input_tokens'] or 0,
                    'output_used': token_usage['output_tokens'] or 0,
                    'used': tokens_used,
                    'remaining': max(daily_token_limit - tokens_used, 0)
                    if daily_token_limit is not None else None,
                },
                'checkout_status': checkout.status if checkout else '',
                'payment_amount': str(subscription.payment.amount) if subscription.payment_id else '',
                'payment_currency': subscription.payment.currency if subscription.payment_id else '',
                'payment_id': subscription.payment.provider_payment_id if subscription.payment_id else '',
            })
            detailed_subscriptions.append(serialized)

        return Response({
            'requests': EnterpriseInquiryAdminSerializer(inquiries, many=True).data,
            'administrators': [
                {'id': str(user.pk), 'name': user.get_full_name() or user.username}
                for user in get_user_model().objects.filter(is_superuser=True, is_active=True).order_by('username')
            ],
            'customers': customers,
            'plans': EnterprisePlanAdminSerializer(Plan.objects.filter(enterprise_inquiries__isnull=False).distinct().order_by('-created_at'), many=True).data,
            'subscriptions': detailed_subscriptions,
            'payments': PaymentSerializer(Payment.objects.select_related(
                'subscription__plan', 'subscription__organization', 'checkout__plan',
            ).order_by('-created_at'), many=True).data,
            'invoice_settings': {
                'invoice_issuer_name': platform_settings.invoice_issuer_name,
                'invoice_issuer_address': platform_settings.invoice_issuer_address,
                'invoice_issuer_gstin': platform_settings.invoice_issuer_gstin,
                'invoice_sac_hsn_code': platform_settings.invoice_sac_hsn_code,
                'invoice_gst_rate_percent': platform_settings.invoice_gst_rate_percent,
            },
            'invitations': [{
                'checkout_id': str(row.pk),
                'email': row.purchaser_email,
                'status': row.status,
                'payment_mode': row.payment_mode,
                'created_at': row.created_at,
                'expires_at': row.registration_token_expires_at,
                'registration_email_sent_at': row.registration_email_sent_at,
                'registered': row.status == PlanCheckout.Status.COMPLETED,
            } for row in checkouts],
        })

    def patch(self, request, inquiry_id=None):
        if inquiry_id is None:
            settings_serializer = InvoiceIssuerSettingsSerializer(data=request.data.get('invoice_settings', request.data))
            settings_serializer.is_valid(raise_exception=True)
            platform_settings, _ = SubscriptionPlatformSettings.objects.get_or_create(pk=1)
            for field, value in settings_serializer.validated_data.items():
                setattr(platform_settings, field, value)
            platform_settings.updated_by = request.user
            platform_settings.save(update_fields=[*settings_serializer.validated_data.keys(), 'updated_by', 'updated_at'])
            return Response({'invoice_settings': settings_serializer.data})
        inquiry = EnterpriseInquiry.objects.filter(pk=inquiry_id).first()
        if not inquiry:
            return Response({'detail': 'Enterprise request was not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = EnterpriseInquiryAdminSerializer(inquiry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EnterprisePaymentInvoiceDetailsView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def patch(self, request, payment_id):
        payment = Payment.objects.filter(pk=payment_id).first()
        if not payment:
            return Response({'detail': 'Payment was not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PaymentInvoiceDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment.invoice_customer_gstin = serializer.validated_data['invoice_customer_gstin'].strip().upper()
        payment.save(update_fields=['invoice_customer_gstin'])
        return Response({'invoice_customer_gstin': payment.invoice_customer_gstin})


class EnterprisePlanManagementView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def _get_plan(self, plan_id):
        return Plan.objects.filter(pk=plan_id, enterprise_inquiries__isnull=False).distinct().first()

    def get(self, request, plan_id):
        plan = self._get_plan(plan_id)
        if not plan:
            return Response({'detail': 'Enterprise custom plan was not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(EnterprisePlanAdminSerializer(plan).data)

    def patch(self, request, plan_id):
        plan = self._get_plan(plan_id)
        if not plan:
            return Response({'detail': 'Enterprise custom plan was not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = EnterprisePlanUpdateSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(EnterprisePlanAdminSerializer(plan).data)


class EnterprisePlanCreateView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def post(self, request, inquiry_id):
        inquiry = EnterpriseInquiry.objects.filter(pk=inquiry_id).first()
        if not inquiry:
            return Response({'detail': 'Enterprise request was not found.'}, status=status.HTTP_404_NOT_FOUND)
        if inquiry.status != EnterpriseInquiry.Status.APPROVED:
            return Response({'detail': 'Approve the Enterprise request before creating a custom plan.'}, status=status.HTTP_409_CONFLICT)
        if inquiry.custom_plan_id:
            return Response({'detail': 'A custom plan is already associated with this request.'}, status=status.HTTP_409_CONFLICT)
        serializer = EnterprisePlanCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values['customer_email'] != inquiry.email.casefold():
            return Response({'customer_email': ['Use the email address on the selected Enterprise inquiry.']}, status=status.HTTP_400_BAD_REQUEST)
        recurring = values['recurring']
        cycle = values['billing_cycle']
        code = 'enterprise-' + uuid.uuid4().hex[:16]
        plan = Plan.objects.create(
            name=values['name'],
            code=code,
            description=values.get('description', ''),
            currency=values['currency'],
            monthly_price=values['amount'] if cycle == Subscription.BillingCycle.MONTHLY else None,
            yearly_price=values['amount'] if cycle == Subscription.BillingCycle.YEARLY else None,
            max_employees=values['max_employees'],
            max_leads=None,
            features=values['features'],
            storage_limit_mb=values.get('storage_limit_mb'),
            included_services=values['included_services'],
            additional_services=values.get('additional_services', ''),
            terms_conditions=values.get('terms_conditions', ''),
            subscription_total_count=values['duration_count'],
            is_active=False,
        )
        if recurring:
            try:
                provider_plan = create_razorpay_plan(plan, billing_cycle=cycle)
            except (RazorpayConfigurationError, RazorpayProviderError, ValueError, ImportError):
                plan.delete()
                return Response({'detail': 'Razorpay could not create the recurring plan; the draft remains inactive for admin review.'}, status=status.HTTP_502_BAD_GATEWAY)
            plan.razorpay_plan_id = provider_plan['id']
        plan.is_active = True
        plan.save(update_fields=['razorpay_plan_id', 'is_active'])
        inquiry.custom_plan = plan
        inquiry.status = EnterpriseInquiry.Status.PLAN_CREATED
        inquiry.save(update_fields=['custom_plan', 'status'])
        return Response(EnterprisePlanAdminSerializer(plan).data, status=status.HTTP_201_CREATED)


class EnterprisePaymentInvitationView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def post(self, request, inquiry_id):
        inquiry = EnterpriseInquiry.objects.select_related('custom_plan').filter(pk=inquiry_id).first()
        if not inquiry or not inquiry.custom_plan_id:
            return Response({'detail': 'Create an approved custom plan first.'}, status=status.HTTP_409_CONFLICT)
        if inquiry.status not in {EnterpriseInquiry.Status.PLAN_CREATED, EnterpriseInquiry.Status.PAYMENT_PENDING}:
            return Response({'detail': 'This request is not ready for a payment invitation.'}, status=status.HTTP_409_CONFLICT)
        if inquiry.payment_link_email_sent_at:
            return Response({'detail': 'A payment invitation was already emailed for this request.'}, status=status.HTTP_409_CONFLICT)

        plan = inquiry.custom_plan
        if not plan.is_active:
            return Response({'detail': 'Reactivate the custom plan before creating a payment invitation.'}, status=status.HTTP_409_CONFLICT)
        cycle = Subscription.BillingCycle.MONTHLY if plan.monthly_price is not None else Subscription.BillingCycle.YEARLY
        amount = plan.monthly_price if cycle == Subscription.BillingCycle.MONTHLY else plan.yearly_price
        checkout = PlanCheckout.objects.filter(enterprise_inquiry=inquiry).first()
        if checkout and checkout.status in {PlanCheckout.Status.PAID, PlanCheckout.Status.COMPLETED, PlanCheckout.Status.ACTIVATED}:
            return Response({'detail': 'Payment for this inquiry has already been confirmed.'}, status=status.HTTP_409_CONFLICT)
        if not checkout:
            checkout = PlanCheckout.objects.create(
                plan=plan,
                organization=inquiry.organization,
                enterprise_inquiry=inquiry,
                billing_cycle=cycle,
                purchaser_email=inquiry.email,
                customer_name=inquiry.full_name,
                amount=amount,
                currency=plan.currency,
                payment_mode='recurring' if plan.razorpay_plan_id else 'one_time',
                duration_count=plan.subscription_total_count or 1,
                plan_snapshot={
                    'name': plan.name,
                    'max_employees': plan.max_employees,
                    'storage_limit_mb': plan.storage_limit_mb,
                    'features': plan.features,
                    'included_services': plan.included_services,
                    'additional_services': plan.additional_services,
                    'terms_conditions': plan.terms_conditions,
                },
                status=PlanCheckout.Status.CREATING,
            )
        if not checkout.razorpay_order_id and not checkout.razorpay_subscription_id:
            try:
                if checkout.payment_mode == 'recurring':
                    key_id, provider_subscription = create_razorpay_subscription(
                        checkout, total_count=plan.subscription_total_count,
                    )
                    checkout.razorpay_subscription_id = provider_subscription['id']
                    checkout.status = PlanCheckout.Status.PENDING_AUTHORIZATION
                    checkout.save(update_fields=['razorpay_subscription_id', 'status'])
                else:
                    key_id, provider_order = create_razorpay_order(checkout)
                    checkout.razorpay_order_id = provider_order['id']
                    checkout.status = PlanCheckout.Status.PENDING
                    checkout.save(update_fields=['razorpay_order_id', 'status'])
            except (RazorpayConfigurationError, RazorpayProviderError, ValueError, ImportError):
                checkout.status = PlanCheckout.Status.FAILED
                checkout.save(update_fields=['status'])
                return Response({'detail': 'Razorpay could not create the approved payment invitation.'}, status=status.HTTP_502_BAD_GATEWAY)

        raw_token = create_registration_token()
        checkout.enterprise_access_token_hash = hash_registration_token(raw_token)
        checkout.enterprise_access_token_expires_at = timezone.now() + timedelta(hours=48)
        checkout.save(update_fields=['enterprise_access_token_hash', 'enterprise_access_token_expires_at'])
        link = f'{settings.FRONTEND_URL}/?enterprise_checkout={raw_token}'
        body = (
            f'Hello {inquiry.full_name},\n\n'
            f'Your custom plan for {inquiry.organization_name} is ready.\n'
            f'Plan: {plan.name}\nUsers: {plan.max_employees}\nBilling: {cycle}\n'
            f'Amount: {plan.currency} {amount}\nFeatures: {json.dumps(plan.features, ensure_ascii=False)}\n'
            f'Included services: {", ".join(plan.included_services)}\nStorage limit: {plan.storage_limit_mb or "Custom"} MB\n'
            f'Additional services: {plan.additional_services}\nTerms: {plan.terms_conditions}\n\nProceed to payment: {link}'
        )
        try:
            from django.core.mail import send_mail
            sent = send_mail(
                f'Your Auron FIN CRM Enterprise plan: {plan.name}', body,
                settings.DEFAULT_FROM_EMAIL, [inquiry.email], fail_silently=False,
                html_message=(
                    f'<p>Hello {escape(inquiry.full_name)},</p>'
                    f'<p>Your custom plan for {escape(inquiry.organization_name)} is ready.</p>'
                    f'<p><strong>{escape(plan.name)}</strong> · {plan.max_employees} users · {escape(cycle.lower())} · {escape(plan.currency)} {escape(amount)}</p>'
                    f'<p>Features: {escape(json.dumps(plan.features, ensure_ascii=False))}</p>'
                    f'<p>{escape(", ".join(plan.included_services))}</p>'
                    f'<p>{escape(plan.additional_services)}</p>'
                    f'<p>Storage limit: {plan.storage_limit_mb or "Custom"} MB</p>'
                    f'<p>{escape(plan.terms_conditions)}</p>'
                    f'<p><a href="{escape(link)}">Proceed to Payment</a></p>'
                ),
            )
        except Exception:
            sent = 0
        if sent != 1:
            return Response({'detail': 'Payment was prepared but email delivery failed. The invitation is saved; retry from the dashboard.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        inquiry.status = EnterpriseInquiry.Status.PAYMENT_PENDING
        inquiry.payment_link_email_sent_at = timezone.now()
        inquiry.save(update_fields=['status', 'payment_link_email_sent_at'])
        return Response({'detail': 'Payment invitation emailed.', 'payment_mode': checkout.payment_mode}, status=status.HTTP_201_CREATED)


class EnterpriseRegistrationResendView(APIView):
    permission_classes = [IsFinCRMAdministrator]

    def post(self, request, checkout_id):
        checkout = PlanCheckout.objects.select_related('plan', 'enterprise_inquiry', 'organization').filter(
            pk=checkout_id,
            enterprise_inquiry__isnull=False,
            status=PlanCheckout.Status.PAID,
            registration_token_used_at__isnull=True,
        ).first()
        if not checkout:
            return Response({'detail': 'An unused Enterprise registration invitation was not found.'}, status=status.HTTP_404_NOT_FOUND)
        previous_hash = checkout.registration_token_hash
        previous_expiry = checkout.registration_token_expires_at
        raw_token = create_registration_token()
        checkout.registration_token_hash = hash_registration_token(raw_token)
        checkout.registration_token_expires_at = timezone.now() + timedelta(hours=24)
        checkout.save(update_fields=['registration_token_hash', 'registration_token_expires_at'])
        try:
            sent_at = send_registration_link(checkout, raw_token, lifetime=timedelta(hours=24))
        except RegistrationEmailError:
            checkout.registration_token_hash = previous_hash
            checkout.registration_token_expires_at = previous_expiry
            checkout.save(update_fields=['registration_token_hash', 'registration_token_expires_at'])
            return Response({'detail': 'The registration email could not be resent. The previous unused link remains valid.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        checkout.registration_email_sent_at = sent_at
        checkout.save(update_fields=['registration_email_sent_at'])
        return Response({'detail': 'A new 24-hour registration link was sent. The previous link is no longer valid.'})


class EnterpriseCheckoutWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get('X-Razorpay-Signature', '')
        if not valid_webhook_signature(raw_body, signature):
            return Response({'detail': 'Invalid webhook signature.'}, status=status.HTTP_400_BAD_REQUEST)
        event_id = request.headers.get('X-Razorpay-Event-Id', '').strip()
        if not event_id:
            return Response({'detail': 'Missing Razorpay event ID.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError):
            return Response({'detail': 'Invalid webhook payload.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = process_razorpay_event(event_id, payload, hashlib.sha256(raw_body).hexdigest())
        except WebhookProcessingError:
            return Response({'detail': 'Webhook processing failed; delivery can be retried.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'status': result}, status=status.HTTP_200_OK)
