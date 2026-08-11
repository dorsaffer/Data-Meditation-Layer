"""FR6.8: "Access denied events" and unattributable "Authentication
attempts" both surface the same way in DRF - a 401/403 raised out of
permission/authentication checks - so this hooks the single place every
one of those already flows through (settings.REST_FRAMEWORK.
EXCEPTION_HANDLER) instead of adding logging to every permission class
and view individually. Successful authentication is logged separately
(apps.accounts.views.AuditedTokenObtainPairView) since a 200 response
never reaches an exception handler.
"""
from __future__ import annotations

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.views import exception_handler as drf_exception_handler

from .models import AuditEvent
from .services import record_event


def audit_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None and response.status_code in (401, 403):
        request = context.get('request')
        view = context.get('view')
        is_auth_failure = isinstance(exc, (NotAuthenticated, AuthenticationFailed))

        actor = None
        if is_auth_failure and request is not None:
            try:
                actor = request.data.get('username') or None
            except Exception:
                actor = None

        record_event(
            AuditEvent.Action.AUTHENTICATION if is_auth_failure else AuditEvent.Action.ACCESS_DENIED,
            AuditEvent.Outcome.DENIED,
            resource_type=view.__class__.__name__ if view else '',
            actor=actor,
            detail={
                'path': getattr(request, 'path', ''),
                'method': getattr(request, 'method', ''),
            },
            request=request,
        )
    return response
