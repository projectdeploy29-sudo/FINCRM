from django.urls import path, include
from rest_framework.routers import DefaultRouter
from communications.views import InteractionViewSet, InteractionAttendeeViewSet, MessageDraftViewSet

router = DefaultRouter()
router.register(r'interactions', InteractionViewSet, basename='interaction')
router.register(r'attendees', InteractionAttendeeViewSet, basename='interaction_attendee')
router.register(r'drafts', MessageDraftViewSet, basename='message_draft')

urlpatterns = [
    path('', include(router.urls)),
]
