from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RawDHIS2RecordViewSet

router = DefaultRouter()
router.register('raw-records', RawDHIS2RecordViewSet, basename='raw-records')

urlpatterns = [
    path('', include(router.urls)),
]
