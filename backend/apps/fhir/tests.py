from datetime import date
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.data_products.models import District, Indicator, Observation
from apps.dhis2.models import RawDHIS2Record
from apps.fhir.builders import (
    build_bundle,
    build_location,
    build_measure,
    build_measure_report,
    build_organization,
    build_provenance,
    parse_dhis2_period,
)
from apps.fhir.services import FHIRValidationError, validate_resource


class ParseDhis2PeriodTests(SimpleTestCase):
    """Highest-risk pure logic in this app, same category as
    DHIS2Client._parse_analytics: getting a period boundary wrong
    silently produces a MeasureReport with a plausible-looking but
    wrong Period.
    """

    def test_monthly_period(self):
        self.assertEqual(parse_dhis2_period('202508'), (date(2025, 8, 1), date(2025, 8, 31)))

    def test_monthly_period_handles_february_leap_year(self):
        self.assertEqual(parse_dhis2_period('202402'), (date(2024, 2, 1), date(2024, 2, 29)))

    def test_yearly_period(self):
        self.assertEqual(parse_dhis2_period('2025'), (date(2025, 1, 1), date(2025, 12, 31)))

    def test_unsupported_format_raises(self):
        with self.assertRaises(ValueError):
            parse_dhis2_period('2025Q3')


class ResourceBuilderTests(SimpleTestCase):
    """Builders take plain (unsaved) model instances and never touch the
    DB themselves, so these run as SimpleTestCase - same pattern as
    apps/dhis2/tests.py for _parse_analytics.
    """

    def setUp(self):
        self.district = District(dhis2_org_unit_uid='OU_BO', name='Bo')
        self.indicator = Indicator(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        self.observation = Observation(
            indicator=self.indicator, district=self.district, period='202508', value=2875.0,
        )

    def test_build_organization_is_a_valid_shape(self):
        org = build_organization()
        self.assertEqual(org['resourceType'], 'Organization')
        self.assertTrue(org['id'])

    def test_build_location_partof_references_country(self):
        location = build_location(self.district)
        self.assertEqual(location['resourceType'], 'Location')
        self.assertEqual(location['id'], 'district-OU_BO')
        self.assertEqual(location['partOf']['reference'], 'Location/country-sl')

    def test_build_measure_name_is_a_valid_fhir_name_token(self):
        measure = build_measure(self.indicator)
        self.assertEqual(measure['resourceType'], 'Measure')
        self.assertRegex(measure['name'], r'^[A-Za-z][A-Za-z0-9_]*$')
        self.assertEqual(measure['title'], 'ANC 1st visit')

    def test_build_measure_omits_group_code_with_no_codings(self):
        measure = build_measure(self.indicator)
        self.assertNotIn('group', measure)

    def test_build_measure_includes_group_code_when_codings_given(self):
        codings = [{'system': 'http://hl7.org/fhir/sid/icd-10', 'code': 'Z34.9', 'display': 'x', 'version': 'v'}]
        measure = build_measure(self.indicator, codings=codings)
        self.assertEqual(measure['group'], [{'code': {'coding': codings, 'text': 'ANC 1st visit'}}])

    def test_build_measure_report_mirrors_measure_group_code(self):
        codings = [{'system': 'http://hl7.org/fhir/sid/icd-10', 'code': 'Z34.9', 'display': 'x', 'version': 'v'}]
        measure = build_measure(self.indicator, codings=codings)
        report = build_measure_report(self.observation, measure)
        self.assertEqual(report['group'][0]['code'], measure['group'][0]['code'])

    def test_build_measure_report_references_measure_and_location(self):
        measure = build_measure(self.indicator)
        report = build_measure_report(self.observation, measure)
        self.assertEqual(report['resourceType'], 'MeasureReport')
        self.assertEqual(report['type'], 'summary')
        self.assertEqual(report['measure'], measure['url'])
        self.assertEqual(report['subject']['reference'], 'Location/district-OU_BO')
        self.assertEqual(report['group'][0]['measureScore']['value'], 2875.0)
        self.assertEqual(report['period'], {'start': '2025-08-01', 'end': '2025-08-31'})

    def test_build_provenance_targets_every_measure_report(self):
        measure = build_measure(self.indicator)
        report = build_measure_report(self.observation, measure)
        raw = RawDHIS2Record(
            dx_uid='DX_ANC1', dx_name='ANC 1st visit', org_unit_uid='OU_BO', org_unit_name='Bo',
            period='202508', value='2875', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        raw.fetched_at = timezone.now()

        provenance = build_provenance([report], [raw])

        self.assertEqual(provenance['resourceType'], 'Provenance')
        self.assertEqual(provenance['target'], [{'reference': f'MeasureReport/{report["id"]}'}])
        self.assertEqual(provenance['entity'][0]['what']['identifier']['system'], raw.source_url)


class BuildBundleTests(TestCase):
    """build_bundle reads Observations from the DB, so it's the one
    builder that needs a real TestCase.
    """

    def setUp(self):
        self.district = District.objects.create(dhis2_org_unit_uid='OU_BO', name='Bo')
        self.indicator = Indicator.objects.create(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        self.raw = RawDHIS2Record.objects.create(
            dx_uid='DX_ANC1', dx_name='ANC 1st visit', org_unit_uid='OU_BO', org_unit_name='Bo',
            period='202508', value='2875', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=self.indicator, district=self.district, period='202508', value=2875.0,
            source_raw_record=self.raw,
        )

    def test_bundle_includes_one_of_each_resource_type(self):
        bundle = build_bundle(self.indicator)
        resource_types = [entry['resource']['resourceType'] for entry in bundle['entry']]

        self.assertEqual(bundle['resourceType'], 'Bundle')
        self.assertEqual(bundle['type'], 'collection')
        self.assertEqual(resource_types.count('Organization'), 1)
        self.assertEqual(resource_types.count('Location'), 2)  # country + one district
        self.assertEqual(resource_types.count('Measure'), 1)
        self.assertEqual(resource_types.count('MeasureReport'), 1)
        self.assertEqual(resource_types.count('Provenance'), 1)

    def test_bundle_omits_provenance_when_indicator_has_no_observations(self):
        empty_indicator = Indicator.objects.create(dhis2_dx_uid='DX_EMPTY', name='Unused indicator')
        bundle = build_bundle(empty_indicator)
        resource_types = [entry['resource']['resourceType'] for entry in bundle['entry']]
        self.assertNotIn('Provenance', resource_types)
        self.assertNotIn('MeasureReport', resource_types)

    def test_bundle_measure_carries_accepted_terminology_coding_only(self):
        from django.contrib.auth import get_user_model

        from apps.terminology.services import propose_mapping, review_mapping

        proposed = propose_mapping(
            source_system='DHIS2', source_code='DX_ANC1', source_display='ANC 1st visit',
            target_terminology='icd10', target_code='Z34.9',
            target_display='Encounter for supervision of normal pregnancy, unspecified, trimester unspecified',
            terminology_version='ICD-10 2019', rationale='Semantic match on "antenatal".',
        )
        bundle = build_bundle(self.indicator)
        measure = next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'Measure')
        self.assertNotIn('group', measure, 'a PROPOSED mapping must never reach the FHIR export')

        reviewer = get_user_model().objects.create_user(username='steward', password='x')
        review_mapping(proposed, reviewer=reviewer, approve=True, rationale='Confirmed.')

        bundle = build_bundle(self.indicator)
        measure = next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'Measure')
        report = next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'MeasureReport')
        self.assertEqual(measure['group'][0]['code']['coding'][0]['code'], 'Z34.9')
        self.assertEqual(report['group'][0]['code'], measure['group'][0]['code'])


class ValidateResourceTests(SimpleTestCase):
    """The HTTP call to the real validator is mocked here - these tests
    check that we correctly interpret its response, not that HAPI
    itself works (that's what the docker-compose fhir-validator service
    and the export_fhir management command's manual run are for).
    """

    @mock.patch('apps.fhir.services.requests.post')
    def test_no_issues_is_valid(self, mock_post):
        mock_post.return_value.json.return_value = {'resourceType': 'OperationOutcome', 'issue': []}

        result = validate_resource('Organization', {'resourceType': 'Organization'})

        self.assertEqual(result, {'is_valid': True, 'issues': []})

    @mock.patch('apps.fhir.services.requests.post')
    def test_error_severity_issue_is_invalid(self, mock_post):
        issues = [{'severity': 'error', 'diagnostics': 'Missing required field'}]
        mock_post.return_value.json.return_value = {'resourceType': 'OperationOutcome', 'issue': issues}

        result = validate_resource('Measure', {'resourceType': 'Measure'})

        self.assertFalse(result['is_valid'])
        self.assertEqual(result['issues'], issues)

    @mock.patch('apps.fhir.services.requests.post')
    def test_warning_only_issue_is_still_valid(self, mock_post):
        issues = [{'severity': 'warning', 'diagnostics': 'Best practice recommendation'}]
        mock_post.return_value.json.return_value = {'resourceType': 'OperationOutcome', 'issue': issues}

        result = validate_resource('Measure', {'resourceType': 'Measure'})

        self.assertTrue(result['is_valid'])

    @mock.patch('apps.fhir.services.requests.post')
    def test_non_operation_outcome_response_raises(self, mock_post):
        mock_post.return_value.json.return_value = {'resourceType': 'Organization'}

        with self.assertRaises(FHIRValidationError):
            validate_resource('Organization', {'resourceType': 'Organization'})

    @mock.patch('apps.fhir.services.requests.post')
    def test_connection_error_raises(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError('refused')

        with self.assertRaises(FHIRValidationError):
            validate_resource('Organization', {'resourceType': 'Organization'})
