from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.dhis2.models import RawDHIS2Record

from .models import District, Indicator, Observation


class ObservationViewSetPermissionTests(RoleTestMixin, TestCase):
    """analyst and auditor can read Observations; data_provider (and any
    unrecognized/no-role account) cannot - this is the canonical, clean
    analytical dataset, not raw submissions.
    """

    def setUp(self):
        district = District.objects.create(dhis2_org_unit_uid='OU_BO', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid='DX_ANC1', dx_name='ANC 1st visit', org_unit_uid='OU_BO', org_unit_name='Bo',
            period='202508', value='10', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=indicator, district=district, period='202508', value=10.0, source_raw_record=raw,
        )

    def test_analyst_can_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/observations/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/observations/')
        self.assertEqual(response.status_code, 200)

    def test_staff_can_list(self):
        response = self.client_for(self.make_user(is_staff=True)).get('/api/core/observations/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/observations/')
        self.assertEqual(response.status_code, 403)

    def test_no_role_cannot_list(self):
        response = self.client_for(self.make_user()).get('/api/core/observations/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list(self):
        response = APIClient().get('/api/core/observations/')
        self.assertEqual(response.status_code, 401)


class DataProductViewSetPermissionTests(RoleTestMixin, TestCase):
    """Any recognized role can read the catalog - it's how a partner org
    decides whether to request access to the underlying data - but a
    logged-in account with no role assigned still gets nothing.
    """

    def test_data_provider_can_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/data-products/')
        self.assertEqual(response.status_code, 200)

    def test_analyst_can_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/data-products/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/data-products/')
        self.assertEqual(response.status_code, 200)

    def test_no_role_cannot_list(self):
        response = self.client_for(self.make_user()).get('/api/core/data-products/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list(self):
        response = APIClient().get('/api/core/data-products/')
        self.assertEqual(response.status_code, 401)
