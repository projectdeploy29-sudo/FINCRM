from django.contrib import admin
from .models import User,Manager,Teamlead


def platform_admin_access(request):
    """Django admin is a platform console, never an organization console."""
    return bool(request.user.is_active and request.user.is_superuser)


# Organization administrators use the tenant scoped React application. Even
# existing users carrying is_staff must not enter the shared database admin.
admin.site.has_permission = platform_admin_access

admin.site.register(User)
admin.site.register(Manager)
admin.site.register(Teamlead)
