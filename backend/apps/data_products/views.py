from rest_framework import viewsets

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER, HasAnyRole

from .models import DataProduct, Observation
from .serializers import DataProductSerializer, ObservationSerializer


class ObservationViewSet(viewsets.ReadOnlyModelViewSet):
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


class DataProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Governance metadata only, never the underlying data values.
    Any *recognized role* (not just any authenticated account) may see
    this: it's how a partner org decides whether to even request access
    to the actual Observations.
    """
    queryset = DataProduct.objects.select_related('indicator').all()
    serializer_class = DataProductSerializer
    permission_classes = [HasAnyRole(DATA_PROVIDER, ANALYST, AUDITOR)]
