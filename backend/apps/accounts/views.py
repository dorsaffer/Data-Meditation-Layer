from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.models import AuditEvent
from apps.audit.services import record_event


class AuditedTokenObtainPairView(TokenObtainPairView):
    """FR6.8: logs a successful login as an AUTHENTICATION AuditEvent.
    A failed attempt (bad credentials) never reaches here - SimpleJWT's
    serializer raises AuthenticationFailed, which is caught by the DRF
    EXCEPTION_HANDLER instead (apps.audit.exception_handler), the one
    place every 401/403 in the API already flows through.
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            record_event(
                AuditEvent.Action.AUTHENTICATION, AuditEvent.Outcome.SUCCESS,
                resource_type='AuditedTokenObtainPairView',
                actor=request.data.get('username') or None,
                detail={'path': request.path},
                request=request,
            )
        return response


class MeView(APIView):
    """Tells a JWT-authenticated client who they are and which roles
    (Groups) they hold, so the frontend knows what to render/hide
    without having to probe individual endpoints for a 403.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'username': user.username,
            'roles': list(user.groups.values_list('name', flat=True)),
            'is_staff': user.is_staff,
        })
