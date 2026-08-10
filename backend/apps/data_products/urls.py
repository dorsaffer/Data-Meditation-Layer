from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DataProductViewSet, ObservationViewSet

router = DefaultRouter()
router.register('observations', ObservationViewSet, basename='observations')
router.register('data-products', DataProductViewSet, basename='data-products')

urlpatterns = [
    path('', include(router.urls)),
]
