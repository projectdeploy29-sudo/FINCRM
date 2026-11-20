from django.urls import path, include
from rest_framework.routers import DefaultRouter
from communications.views import MessageDraftViewSet

router = DefaultRouter()
router.register(r'drafts', MessageDraftViewSet, basename='message_draft')

urlpatterns = [
    path('', include(router.urls)),
]
