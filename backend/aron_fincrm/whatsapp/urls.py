from django.urls import path

from . import views


urlpatterns = [
    path('templates/', views.templates, name='whatsapp_templates'),
    path('followup-history/', views.followup_history, name='whatsapp_followup_history'),
    path('prepare-followup/', views.prepare_followup, name='whatsapp_prepare_followup'),
]
