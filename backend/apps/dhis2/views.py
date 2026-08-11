from rest_framework import viewsets

from apps.accounts.permissions import AUDITOR, DATA_PROVIDER, HasAnyRole
from apps.audit.mixins import AuditedReadOnlyViewSetMixin

from .models import RawDHIS2Record
from .serializers import RawDHIS2RecordSerializer


class RawDHIS2RecordViewSet(AuditedReadOnlyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only exposure of raw DHIS2 records. This data hasn't been
    through quality/privacy screening yet, so it's gated to the roles
    with a real reason to see it: data_provider (it's their submitted
    source data) and auditor (audit trail). analyst works with the
    cleaned Observations instead (see ObservationViewSet).
    """
    serializer_class = RawDHIS2RecordSerializer
    permission_classes = [HasAnyRole(DATA_PROVIDER, AUDITOR)]

    def get_queryset(self):
        queryset = RawDHIS2Record.objects.all()
        params = self.request.query_params
        for field in ('dx_uid', 'org_unit_uid', 'period'):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
