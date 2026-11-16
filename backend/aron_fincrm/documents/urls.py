from rest_framework.routers import DefaultRouter
from documents.views import DocumentViewSet, DocumentCategoryViewSet
router=DefaultRouter(); router.register('documents',DocumentViewSet,basename='document'); router.register('document-categories',DocumentCategoryViewSet,basename='document-category')
urlpatterns=router.urls
