from rest_framework import permissions, viewsets

from .models import FHIRValidationResult
from .serializers import FHIRValidationResultSerializer


class FHIRValidationResultViewSet(viewsets.ReadOnlyModelViewSet):
    """Conformity evidence for generated FHIR resources. Admin-only,
    same gating as RawDHIS2Record/Observation: fhir_json carries real
    aggregate values, not just governance metadata.
    """
    serializer_class = FHIRValidationResultSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = FHIRValidationResult.objects.all()
        params = self.request.query_params
        for field in ('resource_type', 'is_valid'):
            value = params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
