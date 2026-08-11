from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


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
