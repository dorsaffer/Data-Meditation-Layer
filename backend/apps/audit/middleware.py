"""FR6.8: gives every HTTP request a correlation id, so every AuditEvent
produced while handling it (view logging, permission-denial logging,
downstream service calls) can be tied back to the same request even
though they're logged from different, unrelated call sites.

Accepts an inbound X-Correlation-ID header (so a caller/gateway can
propagate its own id across services) and always echoes the id actually
used back on the response, so a client or auditor can find the matching
AuditEvent rows without having generated the id themselves.
"""
from __future__ import annotations

from .context import _correlation_id, new_correlation_id

REQUEST_HEADER = 'HTTP_X_CORRELATION_ID'
RESPONSE_HEADER = 'X-Correlation-ID'


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.META.get(REQUEST_HEADER) or new_correlation_id()
        request.correlation_id = correlation_id
        token = _correlation_id.set(correlation_id)
        try:
            response = self.get_response(request)
        finally:
            _correlation_id.reset(token)
        response[RESPONSE_HEADER] = correlation_id
        return response
