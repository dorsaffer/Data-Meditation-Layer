from rest_framework import viewsets

from apps.accounts.permissions import ANALYST, AUDITOR, HasAnyRole

from .models import AuditEvent, ProvenanceRecord
from .serializers import AuditEventSerializer, ProvenanceRecordSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """FR6.8: the audit trail itself. Gated to auditor only (plus the
    staff/superuser operator bypass every HasAnyRole check has) - unlike
    the catalog/mapping endpoints, this is not "any recognized role", it
    is specifically the role whose job is oversight of the others.
    Deliberately does NOT use AuditedReadOnlyViewSetMixin: logging a
    DATASET_VIEW event every time someone reads the audit log itself
    would just be noise chasing its own tail.
    """
    serializer_class = AuditEventSerializer
    permission_classes = [HasAnyRole(AUDITOR)]

    def get_queryset(self):
        queryset = AuditEvent.objects.all()
        params = self.request.query_params
        field_map = {
            'actor': 'actor', 'action': 'action', 'outcome': 'outcome',
            'resource_type': 'resource_type', 'correlation_id': 'correlation_id',
        }
        for param, lookup in field_map.items():
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset


class ProvenanceRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """FR6.8: data lineage, kept separate from AuditEvent (see
    models.py's module docstring). Gated to analyst and auditor - the
    same "works with the data day to day" / "oversight" split
    apps.terminology's mapping catalog already uses.
    """
    serializer_class = ProvenanceRecordSerializer
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get_queryset(self):
        queryset = ProvenanceRecord.objects.all()
        params = self.request.query_params
        field_map = {'data_product': 'data_product_id', 'activity': 'activity'}
        for param, lookup in field_map.items():
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset
