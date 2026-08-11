"""The only writer of AuditEvent/ProvenanceRecord rows - every call site
in the codebase (views, permission-denial handling, pipeline services,
admin actions) goes through record_event()/record_provenance() rather
than creating the models directly, so actor/organisation/correlation-id
resolution stays in one place.
"""
from __future__ import annotations

from .context import get_actor, get_correlation_id, get_organisation
from .models import AuditEvent, ProvenanceRecord


def _actor_label(request, actor: str | None) -> str:
    if actor:
        return actor
    if request is not None:
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return user.username
        return 'anonymous'
    return get_actor()


def _correlation_label(request, correlation_id: str | None) -> str:
    if correlation_id:
        return correlation_id
    if request is not None:
        existing = getattr(request, 'correlation_id', None)
        if existing:
            return existing
    return get_correlation_id()


def record_event(
    action: str, outcome: str, *,
    resource_type: str = '', resource_id=None,
    actor: str | None = None, organisation: str | None = None,
    detail: dict | None = None, request=None, correlation_id: str | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=_actor_label(request, actor),
        organisation=organisation if organisation is not None else get_organisation(),
        action=action,
        resource_type=resource_type,
        resource_id='' if resource_id in (None, '') else str(resource_id),
        outcome=outcome,
        correlation_id=_correlation_label(request, correlation_id),
        detail=detail or {},
    )


def record_provenance(
    *, activity: str, description: str, data_product=None,
    resource_type: str = '', resource_id=None, source_reference: str = '',
    performed_by: str | None = None, correlation_id: str | None = None,
) -> ProvenanceRecord:
    return ProvenanceRecord.objects.create(
        data_product=data_product,
        resource_type=resource_type,
        resource_id='' if resource_id in (None, '') else str(resource_id),
        activity=activity,
        description=description,
        source_reference=source_reference,
        performed_by=performed_by or get_actor(),
        correlation_id=correlation_id or get_correlation_id(),
    )
