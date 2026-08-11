from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TerminologyMappingViewSet

router = DefaultRouter()
router.register('terminology-mappings', TerminologyMappingViewSet, basename='terminology-mappings')

urlpatterns = [
    path('', include(router.urls)),
]
