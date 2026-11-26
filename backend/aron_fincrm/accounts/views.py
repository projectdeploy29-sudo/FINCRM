from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.html import escape
from datetime import timedelta
from accounts.models import PasswordResetRequest
from accounts.serializers import (
    CustomTokenObtainPairSerializer,
    UserMeSerializer,
    ChangePasswordSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Returns JWT tokens with enriched claims, organization context, and user permissions.
    """
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    """Revoke a refresh token presented by its holder during sign-out."""
    # Refresh tokens are credentials themselves, so logout must also work after
    # the short-lived access token expires.
    permission_classes = [AllowAny]

    def post(self, request):
        raw_token = request.data.get('refresh')
        if not isinstance(raw_token, str) or not raw_token:
            return Response({'refresh': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(raw_token)
            token_user_id = str(refresh.payload.get('user_id'))
            if request.user.is_authenticated and token_user_id != str(request.user.pk):
                return Response({'detail': 'Invalid refresh token.'}, status=status.HTTP_400_BAD_REQUEST)
            refresh.blacklist()
        except TokenError:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class UserMeView(APIView):
    """
    GET /api/v1/auth/me/
    Returns the profile and organizational RBAC context of the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserMeSerializer(request.user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserMeSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Allows an authenticated user to change their password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'user': request.user})
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response(
                    {"old_password": ["Incorrect current password."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response(
                {"detail": "Password successfully updated."},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = str(request.data.get('email', '')).strip()
        if not email or '@' not in email:
            return Response({'email': ['Enter a valid email address.']}, status=status.HTTP_400_BAD_REQUEST)
        User = get_user_model()
        if request.user.is_authenticated:
            email_accounts = User.objects.filter(email__iexact=email, is_active=True)
            if not email_accounts.filter(pk=request.user.pk).exists():
                return Response(
                    {'detail': 'This email does not match the email registered to your signed-in account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = request.user
        else:
            username = str(request.data.get('username', '')).strip()
            if not username:
                return Response({'username': ['Enter your username.']}, status=status.HTTP_400_BAD_REQUEST)
            user = User.objects.filter(username=username, is_active=True).first()
            if not user or not user.email or user.email.casefold() != email.casefold():
                return Response(
                    {'detail': 'The username and email do not match an active account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        now = timezone.now()
        previous = PasswordResetRequest.objects.filter(user=user).first()
        if previous and now < previous.created_at + timedelta(hours=12):
            seconds = int((previous.created_at + timedelta(hours=12) - now).total_seconds())
            hours, remainder = divmod(seconds, 3600)
            minutes = (remainder + 59) // 60
            return Response({'detail': f'A reset link was already sent. You can request another in {hours} hours and {minutes} minutes.', 'retry_after_seconds': seconds}, status=429)
        token = default_token_generator.make_token(user)
        reset_url = f"{settings.FRONTEND_URL}/?reset_uid={user.pk}&reset_token={token}"
        send_mail(
            'Reset your Auron FIN CRM password',
            (
                'Hello,\n\n'
                'We received a request to reset the password for your Auron FIN CRM account. '
                'Use the secure link below to choose a new password:\n\n'
                f'{reset_url}\n\n'
                'For your security, this link expires in 12 hours and can only be used once. '
                'If you did not request a password reset, you can ignore this email; your password will remain unchanged.\n\n'
                'Kind regards,\nAuron FIN CRM Support · Alpha Auron'
            ),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=(
                '<div style="margin:0;background:#f4f6fa;padding:32px 16px;font-family:Arial,sans-serif;color:#202940">'
                '<div style="max-width:600px;margin:0 auto;border:1px solid #e3e7ef;border-radius:12px;background:#fff;overflow:hidden">'
                '<div style="padding:20px 26px;background:#171d35;color:#fff;font-size:20px;font-weight:700">AURON FIN CRM</div>'
                '<div style="padding:28px 26px">'
                '<h1 style="margin:0 0 16px;font-size:23px;color:#171d35">Reset your password</h1>'
                '<p style="margin:0 0 14px;line-height:1.6">We received a request to reset the password for your Auron FIN CRM account.</p>'
                f'<p style="margin:22px 0"><a href="{escape(reset_url)}" style="display:inline-block;padding:12px 18px;border-radius:8px;background:#ec303b;color:#fff;text-decoration:none;font-weight:700">Choose a new password</a></p>'
                '<p style="margin:0 0 12px;line-height:1.6;color:#68758b">This secure link expires in 12 hours and can only be used once.</p>'
                '<p style="margin:0;line-height:1.6;color:#68758b">If you did not request a password reset, you can ignore this email. Your password will remain unchanged.</p>'
                '<p style="margin:24px 0 0;line-height:1.6">Kind regards,<br><strong>Auron FIN CRM Support · Alpha Auron</strong></p>'
                '</div></div></div>'
            ),
        )
        PasswordResetRequest.objects.update_or_create(user=user, defaults={'created_at': now})
        return Response({'detail': 'A password reset email has been sent to your registered address.'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        User = get_user_model()
        user = User.objects.filter(pk=request.data.get('uid'), is_active=True).first()
        token = request.data.get('token', '')
        password = request.data.get('password', '')
        if not user or not default_token_generator.check_token(user, token):
            return Response({'detail': 'This reset link is invalid or expired.'}, status=400)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try: validate_password(password, user)
        except ValidationError as error: return Response({'password': error.messages}, status=400)
        user.set_password(password)
        user.save(update_fields=['password'])
        PasswordResetRequest.objects.filter(user=user).delete()
        return Response({'detail': 'Password reset. Please sign in.'})
