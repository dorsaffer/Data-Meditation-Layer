from rest_framework import permissions, viewsets

from .models import RawDHIS2Record
from .serializers import RawDHIS2RecordSerializer


class RawDHIS2RecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only exposure of raw DHIS2 records. Admin-only: this data
    hasn't been through quality/privacy screening yet, so partner-org
    and researcher roles must never see it. Uses is_staff (DRF's
    IsAdminUser) as the admin proxy for now, until organisation-aware
    roles (assessment doc section 6.8) replace it.
    """
    serializer_class = RawDHIS2RecordSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = RawDHIS2Record.objects.all()
        params = self.request.query_params
        for field in ('dx_uid', 'org_unit_uid', 'period'):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
