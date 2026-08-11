import csv
import tempfile

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.data_products.models import District, Indicator, Observation
from apps.dhis2.models import RawDHIS2Record

from .models import DistrictPopulation, DistrictPopulationMapping, PopulationDataQualityIssue, RawPopulationRecord
from .services import compute_service_coverage, import_population_csv, reconcile_population


def _write_csv(rows):
    fd_path = tempfile.mkstemp(suffix='.csv')[1]
    with open(fd_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['region', 'district', 'male', 'female', 'total', 'sex_ratio'])
        writer.writeheader()
        writer.writerows(rows)
    return fd_path


class ImportPopulationCsvTests(TestCase):
    def test_creates_raw_records(self):
        path = _write_csv([
            {'region': 'SOUTH', 'district': 'Bo', 'male': 100, 'female': 100, 'total': 200, 'sex_ratio': 100.0},
        ])
        result = import_population_csv(path, reference_year=2021)
        self.assertEqual(result, {'created': 1, 'updated': 0, 'conflicts': 0})
        record = RawPopulationRecord.objects.get(district_name='Bo', reference_year=2021)
        self.assertEqual(record.total, 200)

    def test_reimport_with_same_total_updates_not_duplicates(self):
        path = _write_csv([
            {'region': 'SOUTH', 'district': 'Bo', 'male': 100, 'female': 100, 'total': 200, 'sex_ratio': 100.0},
        ])
        import_population_csv(path, reference_year=2021)
        result = import_population_csv(path, reference_year=2021)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(RawPopulationRecord.objects.count(), 1)

    def test_reimport_with_different_total_flags_conflict_and_keeps_existing(self):
        path = _write_csv([
            {'region': 'SOUTH', 'district': 'Bo', 'male': 100, 'female': 100, 'total': 200, 'sex_ratio': 100.0},
        ])
        import_population_csv(path, reference_year=2021)

        conflicting_path = _write_csv([
            {'region': 'SOUTH', 'district': 'Bo', 'male': 150, 'female': 150, 'total': 300, 'sex_ratio': 100.0},
        ])
        result = import_population_csv(conflicting_path, reference_year=2021)

        self.assertEqual(result['conflicts'], 1)
        record = RawPopulationRecord.objects.get(district_name='Bo', reference_year=2021)
        self.assertEqual(record.total, 200)
        self.assertTrue(
            PopulationDataQualityIssue.objects.filter(
                issue_type=PopulationDataQualityIssue.IssueType.DUPLICATE_RECORD, district_name='Bo',
            ).exists()
        )


class ReconcilePopulationTests(TestCase):
    """Exercises the real 12-exact/1-aggregate/2-unmatched shape of this
    integration at small scale: an exact match, an aggregate match (two
    population rows into one DHIS2 district), a documented unmatched
    district, a DHIS2 district with a mapping-worthy name but no
    contributing population row (-> missing_population), and a district
    with no mapping row at all (-> unknown_district) plus a deliberately
    inconsistent row (-> conflicting_identifier).

    Uses "TestX"-prefixed district names throughout, distinct from the
    real 16 names seeded by migrations/0002_seed_district_mapping.py
    (which also runs against the test database), so these fixtures never
    collide with the real seeded mapping rows.
    """

    def setUp(self):
        self.exact_district = District.objects.create(dhis2_org_unit_uid='OU_TEST_EXACT', name='TestExactDistrict')
        self.aggregate_district = District.objects.create(dhis2_org_unit_uid='OU_TEST_AGG', name='TestAggregateDistrict')
        self.orphan_district = District.objects.create(dhis2_org_unit_uid='OU_TEST_ORPHAN', name='TestOrphanDistrict')

        DistrictPopulationMapping.objects.create(
            population_district_name='TestExactSource', dhis2_district=self.exact_district,
            match_type=DistrictPopulationMapping.MatchType.EXACT,
        )
        DistrictPopulationMapping.objects.create(
            population_district_name='TestAggregateSourceA', dhis2_district=self.aggregate_district,
            dhis2_district_hint='TestAggregateDistrict', match_type=DistrictPopulationMapping.MatchType.AGGREGATE,
        )
        DistrictPopulationMapping.objects.create(
            population_district_name='TestAggregateSourceB', dhis2_district=self.aggregate_district,
            dhis2_district_hint='TestAggregateDistrict', match_type=DistrictPopulationMapping.MatchType.AGGREGATE,
        )
        DistrictPopulationMapping.objects.create(
            population_district_name='TestUnmatchedSource', match_type=DistrictPopulationMapping.MatchType.UNMATCHED,
            notes='No DHIS2 counterpart.',
        )
        # TestOrphanDistrict intentionally has no mapping row pointing at it.

        RawPopulationRecord.objects.create(
            region='SOUTH', district_name='TestExactSource', male=100, female=100, total=200, sex_ratio=100.0,
            reference_year=2021,
        )
        RawPopulationRecord.objects.create(
            region='WESTERN', district_name='TestAggregateSourceA', male=300, female=300, total=600, sex_ratio=100.0,
            reference_year=2021,
        )
        RawPopulationRecord.objects.create(
            region='WESTERN', district_name='TestAggregateSourceB', male=250, female=250, total=500, sex_ratio=100.0,
            reference_year=2021,
        )
        RawPopulationRecord.objects.create(
            region='NORTH EAST', district_name='TestUnmatchedSource', male=50, female=50, total=100, sex_ratio=100.0,
            reference_year=2021,
        )
        # No mapping row exists for 'TestBadRow' at all, and its figures don't add up.
        RawPopulationRecord.objects.create(
            region='SOUTH', district_name='TestBadRow', male=10, female=10, total=999, sex_ratio=100.0,
            reference_year=2021,
        )

    def test_aggregates_multiple_population_rows_into_one_dhis2_district(self):
        reconcile_population(reference_year=2021)
        aggregate_population = DistrictPopulation.objects.get(district=self.aggregate_district, reference_year=2021)
        self.assertEqual(aggregate_population.total_population, 1100)
        self.assertEqual(aggregate_population.source_record_count, 2)

    def test_exact_match_reconciles(self):
        reconcile_population(reference_year=2021)
        exact_population = DistrictPopulation.objects.get(district=self.exact_district, reference_year=2021)
        self.assertEqual(exact_population.total_population, 200)

    def test_documented_unmatched_district_produces_issue_and_no_population_row(self):
        reconcile_population(reference_year=2021)
        self.assertFalse(
            DistrictPopulation.objects.filter(reference_year=2021, district=self.orphan_district).exists()
        )
        self.assertTrue(
            PopulationDataQualityIssue.objects.filter(
                issue_type=PopulationDataQualityIssue.IssueType.UNKNOWN_DISTRICT, district_name='TestUnmatchedSource',
            ).exists()
        )

    def test_district_with_no_mapping_at_all_is_unknown_district(self):
        reconcile_population(reference_year=2021)
        self.assertTrue(
            PopulationDataQualityIssue.objects.filter(
                issue_type=PopulationDataQualityIssue.IssueType.UNKNOWN_DISTRICT, district_name='TestBadRow',
            ).exists()
        )

    def test_dhis2_district_with_no_contributing_population_is_missing_population(self):
        reconcile_population(reference_year=2021)
        self.assertTrue(
            PopulationDataQualityIssue.objects.filter(
                issue_type=PopulationDataQualityIssue.IssueType.MISSING_POPULATION,
                district_name='TestOrphanDistrict',
            ).exists()
        )

    def test_inconsistent_male_female_total_is_conflicting_identifier(self):
        reconcile_population(reference_year=2021)
        self.assertTrue(
            PopulationDataQualityIssue.objects.filter(
                issue_type=PopulationDataQualityIssue.IssueType.CONFLICTING_IDENTIFIER, district_name='TestBadRow',
            ).exists()
        )

    def test_rerunning_replaces_rather_than_accumulates_issues(self):
        reconcile_population(reference_year=2021)
        first_count = PopulationDataQualityIssue.objects.count()
        reconcile_population(reference_year=2021)
        self.assertEqual(PopulationDataQualityIssue.objects.count(), first_count)


class StaleAndOutOfPeriodTests(TestCase):
    def setUp(self):
        self.district = District.objects.create(dhis2_org_unit_uid='OU_TEST_STALE', name='TestStaleDistrict')
        self.indicator = Indicator.objects.create(dhis2_dx_uid='DX1', name='Test indicator')
        DistrictPopulationMapping.objects.create(
            population_district_name='TestStaleSource', dhis2_district=self.district,
            match_type=DistrictPopulationMapping.MatchType.EXACT,
        )
        RawPopulationRecord.objects.create(
            region='SOUTH', district_name='TestStaleSource', male=100, female=100, total=200, sex_ratio=100.0,
            reference_year=2021,
        )

    def _create_observation(self, period):
        raw = RawDHIS2Record.objects.create(
            dx_uid='DX1', dx_name='Test indicator', org_unit_uid='OU_TEST_STALE', org_unit_name='TestStaleDistrict',
            period=period, value='10', raw_payload={}, source_url='https://example.test',
        )
        Observation.objects.create(
            indicator=self.indicator, district=self.district, period=period, value=10.0, source_raw_record=raw,
        )

    def test_stale_and_out_of_period_flagged_for_a_multi_year_gap(self):
        self._create_observation('202601')
        reconcile_population(reference_year=2021)
        issue_types = set(PopulationDataQualityIssue.objects.values_list('issue_type', flat=True))
        self.assertIn(PopulationDataQualityIssue.IssueType.STALE_DATA, issue_types)
        self.assertIn(PopulationDataQualityIssue.IssueType.OUT_OF_PERIOD, issue_types)

    def test_no_stale_or_out_of_period_flag_when_reference_year_matches_observation_year(self):
        self._create_observation('202106')
        reconcile_population(reference_year=2021)
        issue_types = set(PopulationDataQualityIssue.objects.values_list('issue_type', flat=True))
        self.assertNotIn(PopulationDataQualityIssue.IssueType.STALE_DATA, issue_types)
        self.assertNotIn(PopulationDataQualityIssue.IssueType.OUT_OF_PERIOD, issue_types)


class ComputeServiceCoverageTests(TestCase):
    def setUp(self):
        self.indicator = Indicator.objects.create(dhis2_dx_uid='DX1', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid='DX1', dx_name='ANC 1st visit', org_unit_uid='OU_X', org_unit_name='X',
            period='202601', value='1', raw_payload={}, source_url='https://example.test',
        )

        # ratios: Kono 2% (lowest), Kenema 5%, Bombali 8%, Bo 10%
        specs = [('Bo', 1000, 100), ('Kenema', 1000, 50), ('Kono', 1000, 20), ('Bombali', 1000, 80)]
        for i, (name, pop, value) in enumerate(specs):
            district = District.objects.create(dhis2_org_unit_uid=f'OU_{i}', name=name)
            DistrictPopulation.objects.create(district=district, total_population=pop, reference_year=2021)
            Observation.objects.create(
                indicator=self.indicator, district=district, period='202601', value=value, source_raw_record=raw,
            )

        no_obs_district = District.objects.create(dhis2_org_unit_uid='OU_NOOBS', name='NoObs')
        DistrictPopulation.objects.create(district=no_obs_district, total_population=500, reference_year=2021)

        no_pop_district = District.objects.create(dhis2_org_unit_uid='OU_NOPOP', name='NoPop')
        Observation.objects.create(
            indicator=self.indicator, district=no_pop_district, period='202601', value=5, source_raw_record=raw,
        )

    def test_computes_ratio_percent(self):
        result = compute_service_coverage(indicator_dx_uid='DX1', period='202601', reference_year=2021)
        bo_row = next(r for r in result['rows'] if r['district'] == 'Bo')
        self.assertEqual(bo_row['ratio_percent'], 10.0)
        self.assertFalse(bo_row['excluded'])

    def test_missing_observation_or_population_is_excluded_not_dropped(self):
        result = compute_service_coverage(indicator_dx_uid='DX1', period='202601', reference_year=2021)

        no_obs_row = next(r for r in result['rows'] if r['district'] == 'NoObs')
        self.assertTrue(no_obs_row['excluded'])
        self.assertIn('no DHIS2 observation', no_obs_row['excluded_reason'])

        no_pop_row = next(r for r in result['rows'] if r['district'] == 'NoPop')
        self.assertTrue(no_pop_row['excluded'])
        self.assertIn('no reconciled population', no_pop_row['excluded_reason'])

    def test_bottom_quartile_flagged_as_potentially_underserved(self):
        result = compute_service_coverage(indicator_dx_uid='DX1', period='202601', reference_year=2021)
        underserved = [r['district'] for r in result['rows'] if r['potentially_underserved']]
        self.assertEqual(underserved, ['Kono'])

    def test_caveat_always_present(self):
        result = compute_service_coverage(indicator_dx_uid='DX1', period='202601', reference_year=2021)
        self.assertIn('not a definitive statement', result['caveat'])

    def test_defaults_to_most_recent_indicator_and_period_when_omitted(self):
        result = compute_service_coverage()
        self.assertEqual(result['indicator'], 'ANC 1st visit')
        self.assertEqual(result['period'], '202601')


class PopulationEndpointPermissionTests(RoleTestMixin, TestCase):
    def setUp(self):
        district = District.objects.create(dhis2_org_unit_uid='OU_BO', name='Bo')
        DistrictPopulation.objects.create(district=district, total_population=100, reference_year=2021)
        PopulationDataQualityIssue.objects.create(issue_type=PopulationDataQualityIssue.IssueType.STALE_DATA, detail='x')

    def test_analyst_can_read_district_population(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/district-population/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_read_district_population(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/district-population/')
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_read_quality_issues(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/population-data-quality-issues/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_read_quality_issues(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/population-data-quality-issues/')
        self.assertEqual(response.status_code, 403)

    def test_analyst_can_read_service_coverage(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/service-coverage/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_read_service_coverage(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/service-coverage/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_read_any(self):
        client = APIClient()
        self.assertEqual(client.get('/api/core/district-population/').status_code, 401)
        self.assertEqual(client.get('/api/core/population-data-quality-issues/').status_code, 401)
        self.assertEqual(client.get('/api/core/service-coverage/').status_code, 401)
