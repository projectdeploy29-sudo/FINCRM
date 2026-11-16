"""
URL configuration for aron_fincrm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from organizations.views import HierarchyTreeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/organizations/', include('organizations.urls')),
    path('api/v1/hierarchy/tree/', HierarchyTreeView.as_view(), name='hierarchy_tree_global'),
    path('api/v1/staff/', include('employes.urls')),
    path('api/v1/', include('permitions.urls')),
    path('api/v1/', include('leads.urls')),
    path('api/v1/', include('customers.urls')),
    path('api/v1/communications/', include('communications.urls')),
    path('api/v1/subscriptions/', include('subscriptions.urls')),
    path('api/v1/', include('applications.urls')),
    path('api/v1/documents/', include('documents.urls')),
    path('api/v1/finance/', include('finance.urls')),
    path('api/v1/', include('tasks.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

