from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ANALYST, AUDITOR, HasAnyRole
from apps.audit.mixins import AuditedReadOnlyViewSetMixin

from .models import DistrictPopulation, PopulationDataQualityIssue
from .serializers import DistrictPopulationSerializer, PopulationDataQualityIssueSerializer
from .services import compute_service_coverage


class DistrictPopulationViewSet(AuditedReadOnlyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Canonical, reconciled population per DHIS2 district - gated the
    same as Observations (analyst, auditor): it's analytical data meant
    to be read alongside service-activity figures, not raw ingestion.
    """
    serializer_class = DistrictPopulationSerializer
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get_queryset(self):
        queryset = DistrictPopulation.objects.select_related('district').all()
        reference_year = self.request.query_params.get('reference_year')
        if reference_year:
            queryset = queryset.filter(reference_year=reference_year)
        return queryset


class PopulationDataQualityIssueViewSet(AuditedReadOnlyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """The population-integration data-quality report - gated the same
    as FHIRValidationResult (analyst, auditor): it's a quality report,
    not raw source data.
    """
    serializer_class = PopulationDataQualityIssueSerializer
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get_queryset(self):
        queryset = PopulationDataQualityIssue.objects.all()
        issue_type = self.request.query_params.get('issue_type')
        if issue_type:
            queryset = queryset.filter(issue_type=issue_type)
        return queryset


class ServiceCoverageView(APIView):
    """GET /api/core/service-coverage/?indicator=<dx_uid>&period=<period>&reference_year=<year>
    The derived metric that needs both sources: Service Activity Ratio =
    reported service activity / population, per district, with districts
    missing either side reported (not dropped) and the bottom quartile
    flagged as a potential (not definitive) under-service signal. See
    apps.population.services.compute_service_coverage.
    """
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get(self, request):
        reference_year = request.query_params.get('reference_year')
        result = compute_service_coverage(
            indicator_dx_uid=request.query_params.get('indicator'),
            period=request.query_params.get('period'),
            reference_year=int(reference_year) if reference_year else None,
        )
        return Response(result)
