from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import TerminologyMapping
from .serializers import TerminologyMappingSerializer


class TerminologyMappingViewSet(viewsets.ReadOnlyModelViewSet):
    """FR6.4: read-only view of the mapping catalog. Writes (propose/
    review) happen through the Django admin (see admin.py) or the
    apps.terminology.services functions directly - same "governance
    decisions aren't made through this API" split as DataProduct.

    Any authenticated role may read this: seeing what is/isn't mapped,
    and why, is exactly what "reviewable and auditable" requires - it's
    the underlying Observation values that stay access-gated.
    """
    serializer_class = TerminologyMappingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = TerminologyMapping.objects.select_related('reviewer').all()
        params = self.request.query_params
        for param, lookup in {
            'status': 'status', 'source_system': 'source_system',
            'source_code': 'source_code', 'target_terminology': 'target_terminology',
        }.items():
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset

    @action(detail=False)
    def proposed(self, request):
        """FR6.4: "Proposed mappings are separated from accepted
        mappings" - an explicit endpoint, not just a filter, so the
        two lists can't be confused by a client forgetting a query param.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(status=TerminologyMapping.Status.PROPOSED)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def accepted(self, request):
        queryset = self.filter_queryset(self.get_queryset()).filter(status=TerminologyMapping.Status.ACCEPTED)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
