from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.dhis2.models import RawDHIS2Record

from .models import DataProduct, District, Indicator, Observation, QualityCheckResult
from .privacy import SMALL_CELL_THRESHOLD, is_small_cell, scan_text_for_identifiers
from .quality import run_quality_checks
from .serializers import ObservationSerializer


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


class RunQualityChecksTests(TestCase):
    """run_quality_checks() and the publish/publish-with-warnings/
    blocked decision it computes.
    """

    def _make_clean_product(self):
        district = District.objects.create(dhis2_org_unit_uid='OU1ABCDEFGH', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX1ABCDEFGH', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid=indicator.dhis2_dx_uid, dx_name=indicator.name,
            org_unit_uid=district.dhis2_org_unit_uid, org_unit_name=district.name,
            period='202508', value='10', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=indicator, district=district, period='202508', value=10.0, source_raw_record=raw,
        )
        return DataProduct.objects.create(
            indicator=indicator, title='ANC 1st visit — District Level',
            refresh_date=timezone.now(), governance_reviewed=True,
            sensitivity_classification=DataProduct.SensitivityClassification.PUBLIC,
        )

    def test_publishable_when_all_checks_pass_and_reviewed(self):
        product = self._make_clean_product()
        run_quality_checks(product)
        product.refresh_from_db()
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.PUBLISHABLE)
        self.assertFalse(product.quality_checks.filter(passed=False).exists())

    def test_blocked_when_governance_not_reviewed(self):
        product = self._make_clean_product()
        product.governance_reviewed = False
        product.save(update_fields=['governance_reviewed'])

        run_quality_checks(product)
        product.refresh_from_db()

        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)
        check = product.quality_checks.get(check_code='governance_review')
        self.assertEqual(check.method, QualityCheckResult.Method.HUMAN_REQUIRED)
        self.assertFalse(check.passed)

    def test_blocked_when_no_observations(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX2ABCDEFGH', name='ANC 2nd visit')
        product = DataProduct.objects.create(
            indicator=indicator, title='ANC 2nd visit — District Level', governance_reviewed=True,
        )

        run_quality_checks(product)
        product.refresh_from_db()

        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)
        check = product.quality_checks.get(check_code='completeness')
        self.assertFalse(check.passed)
        self.assertEqual(check.severity, QualityCheckResult.Severity.BLOCKER)

    def test_invalid_period_format_detected(self):
        product = self._make_clean_product()
        Observation.objects.filter(indicator=product.indicator).update(period='2025-08')
        RawDHIS2Record.objects.filter(dx_uid=product.indicator.dhis2_dx_uid).update(period='2025-08')

        run_quality_checks(product)

        check = product.quality_checks.get(check_code='valid_period_format')
        self.assertFalse(check.passed)
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)

    def test_impossible_negative_value_detected(self):
        product = self._make_clean_product()
        Observation.objects.filter(indicator=product.indicator).update(value=-5.0)

        run_quality_checks(product)

        check = product.quality_checks.get(check_code='impossible_values')
        self.assertFalse(check.passed)
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)

    def test_publishable_with_warnings_on_stale_data(self):
        product = self._make_clean_product()
        product.refresh_date = timezone.now() - timedelta(days=200)
        product.save(update_fields=['refresh_date'])

        run_quality_checks(product)
        product.refresh_from_db()

        stale_check = product.quality_checks.get(check_code='stale_data')
        self.assertFalse(stale_check.passed)
        self.assertEqual(stale_check.severity, QualityCheckResult.Severity.WARNING)
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.PUBLISHABLE_WITH_WARNINGS)

    def test_recompute_is_idempotent(self):
        product = self._make_clean_product()
        run_quality_checks(product)
        first_count = product.quality_checks.count()

        run_quality_checks(product)

        self.assertEqual(product.quality_checks.count(), first_count)


class DataProductQualityApiTests(RoleTestMixin, TestCase):
    """quality_checks and governance_reviewed must be visible through the
    same DataProductViewSet RBAC already covered by
    DataProductViewSetPermissionTests - no new endpoint, no new gating.
    """

    def setUp(self):
        district = District.objects.create(dhis2_org_unit_uid='OU1ABCDEFGH', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX1ABCDEFGH', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid=indicator.dhis2_dx_uid, dx_name=indicator.name,
            org_unit_uid=district.dhis2_org_unit_uid, org_unit_name=district.name,
            period='202508', value='10', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=indicator, district=district, period='202508', value=10.0, source_raw_record=raw,
        )
        self.product = DataProduct.objects.create(
            indicator=indicator, title='ANC 1st visit — District Level',
            refresh_date=timezone.now(), governance_reviewed=True,
            sensitivity_classification=DataProduct.SensitivityClassification.PUBLIC,
        )
        run_quality_checks(self.product)

    def test_analyst_sees_quality_checks_and_governance_reviewed(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/data-products/')
        self.assertEqual(response.status_code, 200)
        body = response.json()[0]
        self.assertEqual(body['quality_status'], DataProduct.QualityStatus.PUBLISHABLE)
        self.assertTrue(body['governance_reviewed'])
        self.assertGreater(len(body['quality_checks']), 0)
        self.assertIn('method', body['quality_checks'][0])
        self.assertIn('severity', body['quality_checks'][0])


class ScanTextForIdentifiersTests(TestCase):
    """FR6.7: the regex layer behind the pii_free_text_scan check."""

    def test_clean_text_has_no_findings(self):
        self.assertEqual(scan_text_for_identifiers('Reported service activity by district.'), [])

    def test_detects_email_address(self):
        self.assertIn('email address', scan_text_for_identifiers('Contact steward at jane.doe@moh.gov.sl.'))

    def test_detects_phone_number(self):
        self.assertIn('phone number', scan_text_for_identifiers('Call +232 76 123 456 for questions.'))

    def test_detects_pii_field_label_leakage(self):
        findings = scan_text_for_identifiers('Patient Name: John Kamara, DOB: 1990-01-01')
        self.assertIn('PII field-label leakage', findings)

    def test_empty_text_has_no_findings(self):
        self.assertEqual(scan_text_for_identifiers(''), [])


class IsSmallCellTests(TestCase):
    def test_value_below_threshold_is_small_cell(self):
        self.assertTrue(is_small_cell(SMALL_CELL_THRESHOLD - 1))

    def test_value_at_threshold_is_not_small_cell(self):
        self.assertFalse(is_small_cell(SMALL_CELL_THRESHOLD))

    def test_value_above_threshold_is_not_small_cell(self):
        self.assertFalse(is_small_cell(SMALL_CELL_THRESHOLD + 1))


class RunPrivacyChecksTests(TestCase):
    """run_privacy_checks(), invoked from run_quality_checks(),
    and how its findings feed the same publish/blocked decision as the
    FR6.6 checks.
    """

    def _make_clean_product(self, *, purpose='Supports UHC analysis by district.', value=10.0):
        district = District.objects.create(dhis2_org_unit_uid='OU1ABCDEFGH', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX1ABCDEFGH', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid=indicator.dhis2_dx_uid, dx_name=indicator.name,
            org_unit_uid=district.dhis2_org_unit_uid, org_unit_name=district.name,
            period='202508', value=str(value), raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=indicator, district=district, period='202508', value=value, source_raw_record=raw,
        )
        return DataProduct.objects.create(
            indicator=indicator, title='ANC 1st visit — District Level', purpose=purpose,
            refresh_date=timezone.now(), governance_reviewed=True,
            sensitivity_classification=DataProduct.SensitivityClassification.PUBLIC,
        )

    def test_publishable_when_privacy_clean(self):
        product = self._make_clean_product()
        run_quality_checks(product)
        product.refresh_from_db()
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.PUBLISHABLE)
        check = product.quality_checks.get(check_code='privacy_sensitivity_tier_gate')
        self.assertTrue(check.passed)

    def test_default_sensitivity_classification_blocks_publication(self):
        """The model default (PROHIBITED) must fail-closed: a brand new
        DataProduct nobody has classified yet cannot be publishable.
        """
        district = District.objects.create(dhis2_org_unit_uid='OU1ABCDEFGH', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX1ABCDEFGH', name='ANC 1st visit')
        product = DataProduct.objects.create(indicator=indicator, title='Unclassified product')
        self.assertEqual(product.sensitivity_classification, DataProduct.SensitivityClassification.PROHIBITED)

        run_quality_checks(product)
        product.refresh_from_db()

        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)
        check = product.quality_checks.get(check_code='privacy_sensitivity_tier_gate')
        self.assertFalse(check.passed)

    def test_personal_classification_blocks_even_when_everything_else_passes(self):
        product = self._make_clean_product()
        product.sensitivity_classification = DataProduct.SensitivityClassification.PERSONAL
        product.save(update_fields=['sensitivity_classification'])

        run_quality_checks(product)
        product.refresh_from_db()

        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)

    def test_pii_in_free_text_blocks_publication(self):
        product = self._make_clean_product(purpose='Contact data steward at jane.doe@moh.gov.sl for access.')

        run_quality_checks(product)
        product.refresh_from_db()

        self.assertEqual(product.quality_status, DataProduct.QualityStatus.BLOCKED)
        check = product.quality_checks.get(check_code='privacy_pii_free_text_scan')
        self.assertFalse(check.passed)
        self.assertIn('email address', check.detail)

    def test_small_cell_is_a_warning_not_a_blocker(self):
        product = self._make_clean_product(value=SMALL_CELL_THRESHOLD - 1)

        run_quality_checks(product)
        product.refresh_from_db()

        check = product.quality_checks.get(check_code='privacy_small_cell_disclosure_risk')
        self.assertFalse(check.passed)
        self.assertEqual(check.severity, QualityCheckResult.Severity.WARNING)
        self.assertEqual(product.quality_status, DataProduct.QualityStatus.PUBLISHABLE_WITH_WARNINGS)


class ObservationSerializerSuppressionTests(TestCase):
    """The functional control itself - small-cell values must
    never reach the serialized API response as their true value.
    """

    def _make_observation(self, value):
        district = District.objects.create(dhis2_org_unit_uid='OU1ABCDEFGH', name='Bo')
        indicator = Indicator.objects.create(dhis2_dx_uid='DX1ABCDEFGH', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid=indicator.dhis2_dx_uid, dx_name=indicator.name,
            org_unit_uid=district.dhis2_org_unit_uid, org_unit_name=district.name,
            period='202508', value=str(value), raw_payload={}, source_url='https://example.test/api/analytics',
        )
        return Observation.objects.create(
            indicator=indicator, district=district, period='202508', value=value, source_raw_record=raw,
        )

    def test_small_cell_value_is_generalised_to_threshold(self):
        observation = self._make_observation(2.0)
        data = ObservationSerializer(observation).data
        self.assertEqual(data['value'], SMALL_CELL_THRESHOLD)
        self.assertTrue(data['is_suppressed'])

    def test_normal_value_is_returned_unchanged(self):
        observation = self._make_observation(42.0)
        data = ObservationSerializer(observation).data
        self.assertEqual(data['value'], 42.0)
        self.assertFalse(data['is_suppressed'])
