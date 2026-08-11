"""FR6.8: "Dataset viewing" audit coverage for the read-only API. Mixed
into every ReadOnlyModelViewSet that exposes real data/governance rows
(Observation, DataProduct, RawDHIS2Record, FHIRValidationResult,
TerminologyMapping) - not into the audit log's own viewset, which would
just recursively log itself.

Only wraps list()/retrieve(): the extra @action endpoints some of these
viewsets add (e.g. TerminologyMappingViewSet.proposed) log their own
events explicitly where that's warranted (e.g. DataProductViewSet.
download), rather than this mixin guessing at every custom action's
semantics.
"""
from __future__ import annotations

from .models import AuditEvent
from .services import record_event


class AuditedReadOnlyViewSetMixin:
    def _resource_type(self) -> str:
        serializer_cls = self.get_serializer_class()
        model = getattr(getattr(serializer_cls, 'Meta', None), 'model', None)
        return model.__name__ if model else self.__class__.__name__

    def _log_view(self, request, *, resource_id) -> None:
        record_event(
            AuditEvent.Action.DATASET_VIEW, AuditEvent.Outcome.SUCCESS,
            resource_type=self._resource_type(), resource_id=resource_id,
            detail={'query_params': dict(request.query_params)},
            request=request,
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self._log_view(request, resource_id='')
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._log_view(request, resource_id=kwargs.get('pk'))
        return response
