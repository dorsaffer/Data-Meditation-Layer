from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.dhis2.client import DHIS2Client, DHIS2ClientError


class ParseAnalyticsTests(SimpleTestCase):
    """_parse_analytics is the highest-risk pure logic in the acquisition
    step: it must not assume a fixed column order, and it must not crash
    on a UID with no resolvable name.
    """

    def test_reads_column_order_from_headers_not_position(self):
        # value/pe/ou/dx deliberately out of the "usual" dx,ou,pe,value order
        payload = {
            'headers': [
                {'name': 'value'}, {'name': 'pe'}, {'name': 'ou'}, {'name': 'dx'},
            ],
            'metaData': {'items': {
                'DX_UID': {'name': 'ANC 1st visit'},
                'OU_UID': {'name': 'Bo'},
            }},
            'rows': [['2875', '202508', 'OU_UID', 'DX_UID']],
        }

        records = DHIS2Client._parse_analytics(payload, source_url='https://example.test/api/analytics')

        self.assertEqual(records, [{
            'dx_uid': 'DX_UID',
            'dx_name': 'ANC 1st visit',
            'org_unit_uid': 'OU_UID',
            'org_unit_name': 'Bo',
            'period': '202508',
            'value': '2875',
            'raw_payload': ['2875', '202508', 'OU_UID', 'DX_UID'],
            'source_url': 'https://example.test/api/analytics',
        }])

    def test_falls_back_to_uid_when_name_not_in_metadata(self):
        payload = {
            'headers': [{'name': 'dx'}, {'name': 'ou'}, {'name': 'pe'}, {'name': 'value'}],
            'metaData': {'items': {}},
            'rows': [['UNKNOWN_DX', 'UNKNOWN_OU', '202508', '10']],
        }

        records = DHIS2Client._parse_analytics(payload, source_url='https://example.test')

        self.assertEqual(records[0]['dx_name'], 'UNKNOWN_DX')
        self.assertEqual(records[0]['org_unit_name'], 'UNKNOWN_OU')

    def test_missing_required_column_raises(self):
        payload = {'headers': [{'name': 'dx'}, {'name': 'ou'}, {'name': 'pe'}], 'rows': []}

        with self.assertRaises(DHIS2ClientError):
            DHIS2Client._parse_analytics(payload, source_url='https://example.test')


class RawDHIS2RecordViewSetPermissionTests(RoleTestMixin, TestCase):
    """data_provider and auditor can read raw records; analyst (and any
    unrecognized/no-role account) cannot - raw ingestion hasn't been
    through quality/privacy screening.
    """

    def test_data_provider_can_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 200)

    def test_staff_can_list(self):
        response = self.client_for(self.make_user(is_staff=True)).get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 200)

    def test_analyst_cannot_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 403)

    def test_no_role_cannot_list(self):
        response = self.client_for(self.make_user()).get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list(self):
        response = APIClient().get('/api/core/raw-records/')
        self.assertEqual(response.status_code, 401)
