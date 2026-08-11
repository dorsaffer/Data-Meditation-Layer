from rest_framework import viewsets

from apps.accounts.permissions import ANALYST, AUDITOR, HasAnyRole

from .models import FHIRValidationResult
from .serializers import FHIRValidationResultSerializer


class FHIRValidationResultViewSet(viewsets.ReadOnlyModelViewSet):
    """Conformity evidence for generated FHIR resources: fhir_json
    carries real aggregate values, not just governance metadata, so
    it's gated to analyst and auditor (the same roles that can see the
    underlying Observations), not data_provider.
    """
    serializer_class = FHIRValidationResultSerializer
    permission_classes = [HasAnyRole(ANALYST, AUDITOR)]

    def get_queryset(self):
        queryset = FHIRValidationResult.objects.all()
        params = self.request.query_params
        for field in ('resource_type', 'is_valid'):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
