from rest_framework.routers import DefaultRouter
from applications.views import FinancialApplicationViewSet
router=DefaultRouter(); router.register('applications',FinancialApplicationViewSet,basename='application')
urlpatterns=router.urls
