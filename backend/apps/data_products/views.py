import csv

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER, HasAnyRole
from apps.audit.mixins import AuditedReadOnlyViewSetMixin
from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .models import DataProduct, Observation
from .privacy import SMALL_CELL_THRESHOLD, is_small_cell
from .serializers import DataProductSerializer, ObservationSerializer


class ObservationViewSet(AuditedReadOnlyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Canonical, clean data points - the actual analytical dataset.
    Gated to analyst (that's the role doing the analysis) and auditor
    (audit trail); data_provider sees their raw records instead (see
    apps/dhis2/views.py).
    """
    serializer_class = ObservationSerializer
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get_queryset(self):
        queryset = Observation.objects.select_related('indicator', 'district').all()
        params = self.request.query_params
        field_map = {
            'district': 'district__dhis2_org_unit_uid',
            'indicator': 'indicator__dhis2_dx_uid',
            'period': 'period',
        }
        for param, lookup in field_map.items():
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset


class DataProductViewSet(AuditedReadOnlyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Governance metadata only, never the underlying data values.
    Any *recognized role* (not just any authenticated account) may see
    this: it's how a partner org decides whether to even request access
    to the actual Observations.
    """
    queryset = DataProduct.objects.select_related('indicator').all()
    serializer_class = DataProductSerializer
    permission_classes = [HasAnyRole(DATA_PROVIDER, ANALYST, AUDITOR)]

    @action(detail=True, permission_classes=[HasAnyRole(ANALYST, AUDITOR)])
    def download(self, request, pk=None):
        """FR6.8: "Dataset downloading" - streams this product's
        underlying Observations as CSV. Gated to analyst/auditor, *not*
        the wider data_provider/analyst/auditor set the rest of this
        viewset uses - a CSV of real Observation values must not be more
        broadly available than ObservationViewSet itself is (data_provider
        cannot read Observations there either, see docs/rbac.md), and
        applies the same FR6.7 small-cell suppression as the API/FHIR
        export - never the true value for a cell below threshold.
        """
        product = self.get_object()
        observations = (
            Observation.objects.filter(indicator_id=product.indicator_id).select_related('district', 'indicator')
            if product.indicator_id else Observation.objects.none()
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="data-product-{product.id}-observations.csv"'
        writer = csv.writer(response)
        writer.writerow(['district', 'indicator', 'period', 'value', 'is_suppressed'])
        row_count = 0
        for obs in observations:
            value = SMALL_CELL_THRESHOLD if is_small_cell(obs.value) else obs.value
            writer.writerow([obs.district.name, obs.indicator.name, obs.period, value, is_small_cell(obs.value)])
            row_count += 1

        record_event(
            AuditEvent.Action.DATASET_DOWNLOAD, AuditEvent.Outcome.SUCCESS,
            resource_type='DataProduct', resource_id=product.id,
            detail={'row_count': row_count},
            request=request,
        )
        return response
