"""FR6.8: correlation-id/actor propagation for code paths that don't have
an HTTP request to read them from (management commands, admin actions).

HTTP requests get their correlation id from CorrelationIdMiddleware
(stashed on request.correlation_id) and their actor from request.user -
apps.audit.services reads those directly, it doesn't need this module for
the request path. This module exists for the *other* call sites:
fetch_dhis2_data, transform_to_canonical, export_fhir and admin actions
all call into services (apps.dhis2.services, apps.data_products.services,
apps.data_products.quality, apps.fhir.services) that have no request
object at all, yet still need a stable actor label and a correlation id
that ties every AuditEvent/ProvenanceRecord from one command invocation
together.
"""
from __future__ import annotations

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'audit_correlation_id', default=None,
)
_actor: contextvars.ContextVar[str | None] = contextvars.ContextVar('audit_actor', default=None)
_organisation: contextvars.ContextVar[str] = contextvars.ContextVar('audit_organisation', default='')


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> str:
    """Returns the current context's correlation id, minting one on first
    use so every event within one command run (with no incoming request
    to carry an id) still shares a single id instead of getting a fresh
    one per AuditEvent."""
    value = _correlation_id.get()
    if value is None:
        value = new_correlation_id()
        _correlation_id.set(value)
    return value


def get_actor() -> str:
    return _actor.get() or 'system'


def get_organisation() -> str:
    return _organisation.get()


class audit_context:
    """Context manager for non-HTTP call sites: sets the actor/
    organisation/correlation id that record_event()/record_provenance()
    fall back to when called without an explicit actor or request.

    Usage: ``with audit_context(actor='system:fetch_dhis2_data'): ...``
    """

    def __init__(
        self, *, actor: str | None = None, organisation: str | None = None,
        correlation_id: str | None = None,
    ):
        self._actor = actor
        self._organisation = organisation
        self._correlation_id = correlation_id or new_correlation_id()
        self._tokens: list[tuple[contextvars.ContextVar, contextvars.Token]] = []

    def __enter__(self) -> 'audit_context':
        self._tokens.append((_correlation_id, _correlation_id.set(self._correlation_id)))
        if self._actor is not None:
            self._tokens.append((_actor, _actor.set(self._actor)))
        if self._organisation is not None:
            self._tokens.append((_organisation, _organisation.set(self._organisation)))
        return self

    def __exit__(self, *exc_info) -> None:
        for var, token in reversed(self._tokens):
            var.reset(token)
