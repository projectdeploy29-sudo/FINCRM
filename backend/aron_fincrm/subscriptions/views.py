import uuid
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from subscriptions.models import Plan, Subscription, Payment, PlanCheckout, EnterpriseInquiry
from subscriptions.serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    PaymentSerializer,
    PlanCheckoutSerializer,
    PlanCheckoutVerificationSerializer,
    EnterpriseInquirySerializer,
)
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
)


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
        serializer = PlanCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        plan = Plan.objects.filter(id=values['plan_id'], is_active=True).first()
        if not plan:
            return Response({'detail': 'Choose an active plan.'}, status=status.HTTP_400_BAD_REQUEST)

        cycle = values['billing_cycle']
        amount = plan.monthly_price if cycle == Subscription.BillingCycle.MONTHLY else plan.yearly_price
        if amount is None:
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
        serializer = PlanCheckoutVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        checkout = PlanCheckout.objects.select_related('plan', 'organization').filter(
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
                claimed = PlanCheckout.objects.filter(
                    pk=checkout.pk,
                    status=PlanCheckout.Status.PENDING,
                ).update(status=PlanCheckout.Status.PROCESSING)
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
        ).order_by('-created_at').first()

        if not sub:
            return Response(
                {"detail": "No active subscription found for this organization.", "has_active_subscription": False},
                status=status.HTTP_200_OK,
            )

        serializer = SubscriptionSerializer(sub)
        data = serializer.data
        data['has_active_subscription'] = True
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

    def post(self, request):
        serializer = EnterpriseInquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()
        admin_email = settings.EMAIL_HOST_USER
        if not admin_email or not settings.EMAIL_HOST_PASSWORD:
            return Response(
                {'detail': 'Your inquiry was saved, but email is not configured. Please try again later.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        customer_sent = False
        admin_sent = False
        try:
            customer_sent = send_mail(
                'We received your FINCRM enterprise inquiry',
                f"Hello {inquiry.full_name},\n\nWe received your enterprise inquiry for {inquiry.organization_name}. Our team will contact you soon.\n\nFINCRM",
                settings.DEFAULT_FROM_EMAIL,
                [inquiry.email],
                fail_silently=False,
            ) == 1
        except Exception:
            customer_sent = False

        details = [
            f'Name: {inquiry.full_name}',
            f'Email: {inquiry.email}',
            f'Phone: {inquiry.phone}',
            f'Organization: {inquiry.organization_name}',
            f'Website: {inquiry.website or "—"}',
            f'LinkedIn: {inquiry.linkedin_url or "—"}',
            f'Note: {inquiry.note or "—"}',
        ]
        try:
            admin_sent = send_mail(
                'FINCRM enterprise plan inquiry',
                '\n'.join(details),
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=False,
            ) == 1
        except Exception:
            admin_sent = False

        inquiry.customer_email_sent = customer_sent
        inquiry.admin_email_sent = admin_sent
        inquiry.save(update_fields=['customer_email_sent', 'admin_email_sent'])
        if not (customer_sent and admin_sent):
            return Response(
                {'detail': 'Your inquiry was saved, but one or more emails could not be sent. Check SMTP settings and try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'detail': 'Your inquiry was received. We will contact you soon.'}, status=status.HTTP_201_CREATED)


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticatedTenant, IsOrgAdmin]
    def post(self,request):
        org=get_user_organization(request.user,request)
        sub=Subscription.objects.filter(organization=org,status__in=['active','trialing']).order_by('-created_at').first()
        if not sub:return Response({'detail':'There is no active subscription to cancel.'},status=400)
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
        return Payment.objects.filter(subscription__organization=org).order_by('-created_at')
