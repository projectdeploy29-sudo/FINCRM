from rest_framework import generics, status
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from subscriptions.models import Plan, Subscription, Payment
from subscriptions.serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    SubscribeSerializer,
    PaymentSerializer,
)
from organizations.tenant import get_user_organization
from permitions.permissions import IsAuthenticatedTenant, IsOrgAdmin


class PlanListView(generics.ListAPIView):
    """
    GET /api/v1/subscriptions/plans/
    Lists all available SaaS subscription tiers and features.
    """
    queryset = Plan.objects.filter(is_active=True).order_by('monthly_price')
    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    pagination_class = None


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
        serializer = SubscribeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            sub = serializer.save()
            return Response(SubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
