from rest_framework.routers import DefaultRouter
from finance.views import RepaymentScheduleViewSet, RepaymentPaymentViewSet
router=DefaultRouter(); router.register('schedules',RepaymentScheduleViewSet,basename='schedule'); router.register('payments',RepaymentPaymentViewSet,basename='payment')
urlpatterns=router.urls
