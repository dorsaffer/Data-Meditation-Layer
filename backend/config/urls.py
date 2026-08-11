from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
