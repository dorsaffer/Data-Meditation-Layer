from rest_framework import permissions, viewsets

from .models import DataProduct, Observation
from .serializers import DataProductSerializer, ObservationSerializer


class ObservationViewSet(viewsets.ReadOnlyModelViewSet):
    """Canonical, clean data points. Same access gating as raw records:
    this hasn't been through quality/privacy screening either (a later
    pipeline stage), so it stays admin-only for now.
    """
    serializer_class = ObservationSerializer
    permission_classes = [permissions.IsAdminUser]

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
    Any authenticated role may see this: it's how a partner org decides
    whether to even request access to the actual Observations.
    """
    queryset = DataProduct.objects.select_related('indicator').all()
    serializer_class = DataProductSerializer
    permission_classes = [permissions.IsAuthenticated]
