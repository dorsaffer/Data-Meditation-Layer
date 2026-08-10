from django.test import SimpleTestCase

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
