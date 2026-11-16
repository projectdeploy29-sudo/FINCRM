from rest_framework.routers import DefaultRouter
from applications.views import FinancialApplicationViewSet, ApplicationChecklistViewSet
router=DefaultRouter(); router.register('applications',FinancialApplicationViewSet,basename='application'); router.register('application-checklist',ApplicationChecklistViewSet,basename='application-checklist')
urlpatterns=router.urls
