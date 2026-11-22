from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
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
