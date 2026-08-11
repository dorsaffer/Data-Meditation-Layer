from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FHIRValidationResultViewSet

router = DefaultRouter()
router.register('fhir-validation-results', FHIRValidationResultViewSet, basename='fhir-validation-results')

urlpatterns = [
    path('', include(router.urls)),
]
