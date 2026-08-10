from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RawDHIS2RecordViewSet, health_check

router = DefaultRouter()
router.register('raw-records', RawDHIS2RecordViewSet, basename='raw-records')

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('core/', include(router.urls)),
]
