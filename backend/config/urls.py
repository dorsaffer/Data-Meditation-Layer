from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import AuditedTokenObtainPairView

from .views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    # Both apps mount under the same api/core/ prefix used by the
    # original ticket's acceptance criteria (api/core/raw-records/,
    # api/core/observations/, api/core/data-products/) - kept stable
    # across this app-split refactor rather than renamed to api/dhis2/...
    path('api/core/', include('apps.dhis2.urls')),
    path('api/core/', include('apps.data_products.urls')),
    path('api/core/', include('apps.fhir.urls')),
    path('api/core/', include('apps.terminology.urls')),
    path('api/core/', include('apps.population.urls')),
    # FR6.8: audit-events/provenance-records - same prefix as everything
    # else above, see apps/audit/urls.py.
    path('api/core/', include('apps.audit.urls')),
    # FR6.8: AuditedTokenObtainPairView logs a successful AUTHENTICATION
    # AuditEvent on 200; a failed attempt (bad credentials) is caught by
    # the DRF EXCEPTION_HANDLER instead (apps.audit.exception_handler),
    # since AuthenticationFailed already raises through the same path.
    path('api/auth/token/', AuditedTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # /api/auth/me/ - tells the frontend who's logged in and which roles
    # (Groups) they hold, see apps/accounts/views.py.
    path('api/auth/', include('apps.accounts.urls')),
]
