from django.urls import path

from . import views


urlpatterns = [
    path('templates/', views.templates, name='whatsapp_templates'),
    path('followup-history/', views.followup_history, name='whatsapp_followup_history'),
    path('prepare-followup/', views.prepare_followup, name='whatsapp_prepare_followup'),
    path('lead-history/', views.lead_history, name='whatsapp_lead_history'),
    path('prepare-lead/', views.prepare_lead, name='whatsapp_prepare_lead'),
]
