from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import (
    CustomTokenObtainPairView,
    LogoutView,
    UserMeView,
    ChangePasswordView,
)

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='auth_login'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth_token_refresh'),
    path('me/', UserMeView.as_view(), name='auth_me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth_change_password'),
]
