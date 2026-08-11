from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DistrictPopulationViewSet, PopulationDataQualityIssueViewSet, ServiceCoverageView

router = DefaultRouter()
router.register('district-population', DistrictPopulationViewSet, basename='district-population')
router.register('population-data-quality-issues', PopulationDataQualityIssueViewSet, basename='population-data-quality-issues')

urlpatterns = [
    path('service-coverage/', ServiceCoverageView.as_view(), name='service-coverage'),
    path('', include(router.urls)),
]
