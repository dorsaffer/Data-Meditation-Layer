from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AuditEventViewSet, ProvenanceRecordViewSet

router = DefaultRouter()
router.register('audit-events', AuditEventViewSet, basename='audit-events')
router.register('provenance-records', ProvenanceRecordViewSet, basename='provenance-records')

urlpatterns = [
    path('', include(router.urls)),
]
