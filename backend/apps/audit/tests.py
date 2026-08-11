"""FR6.8: audit logging tests.

Covers: the required security-relevant events actually get recorded (with
the required metadata), successful and denied actions are both captured,
the audit API is restricted to auditors, and AuditEvent/ProvenanceRecord
are genuinely append-only (protected from modification through normal
application operations - not just documented as such).
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.data_products.models import DataProduct, District, Indicator, Observation
from apps.data_products.quality import run_quality_checks
from apps.data_products.services import sync_data_product, transform_raw_records
from apps.dhis2.models import RawDHIS2Record

from .context import audit_context
from .models import AuditEvent, ProvenanceRecord
from .services import record_event, record_provenance


class AuditEventViewSetPermissionTests(RoleTestMixin, TestCase):
    """Only auditor (and staff) may read the audit trail - unlike the
    catalog/mapping endpoints, this is not "any recognized role".
    """

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 200)

    def test_staff_can_list(self):
        response = self.client_for(self.make_user(is_staff=True)).get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 200)

    def test_analyst_cannot_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 403)

    def test_data_provider_cannot_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 403)

    def test_no_role_cannot_list(self):
        response = self.client_for(self.make_user()).get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list(self):
        response = APIClient().get('/api/core/audit-events/')
        self.assertEqual(response.status_code, 401)


class ProvenanceRecordViewSetPermissionTests(RoleTestMixin, TestCase):
    def test_analyst_can_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/provenance-records/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/provenance-records/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/provenance-records/')
        self.assertEqual(response.status_code, 403)


class AuditEventModelTests(TestCase):
    """Required metadata (actor, organisation, action, resource, timestamp,
    outcome, correlation id) is present, and the table is append-only.
    """

    def test_record_event_populates_required_fields(self):
        event = record_event(
            AuditEvent.Action.DATA_ACQUISITION, AuditEvent.Outcome.SUCCESS,
            resource_type='RawDHIS2Record', resource_id=42,
            actor='system:test', organisation='Ministry of Health',
            detail={'count': 3},
        )
        event.refresh_from_db()
        self.assertEqual(event.actor, 'system:test')
        self.assertEqual(event.organisation, 'Ministry of Health')
        self.assertEqual(event.action, AuditEvent.Action.DATA_ACQUISITION)
        self.assertEqual(event.resource_type, 'RawDHIS2Record')
        self.assertEqual(event.resource_id, '42')
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertTrue(event.correlation_id)
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.detail, {'count': 3})

    def test_record_event_without_actor_or_request_falls_back_to_system(self):
        event = record_event(AuditEvent.Action.DATA_TRANSFORMATION, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.actor, 'system')

    def test_audit_context_sets_actor_and_shared_correlation_id(self):
        with audit_context(actor='system:test-command'):
            first = record_event(AuditEvent.Action.DATA_ACQUISITION, AuditEvent.Outcome.SUCCESS)
            second = record_event(AuditEvent.Action.DATA_TRANSFORMATION, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(first.actor, 'system:test-command')
        self.assertEqual(second.actor, 'system:test-command')
        self.assertEqual(first.correlation_id, second.correlation_id)

    def test_successful_and_denied_outcomes_both_recorded(self):
        record_event(AuditEvent.Action.DATASET_PUBLICATION, AuditEvent.Outcome.SUCCESS, resource_type='DataProduct')
        record_event(AuditEvent.Action.DATASET_PUBLICATION, AuditEvent.Outcome.DENIED, resource_type='DataProduct')
        self.assertEqual(AuditEvent.objects.filter(outcome=AuditEvent.Outcome.SUCCESS).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(outcome=AuditEvent.Outcome.DENIED).count(), 1)

    def test_audit_event_cannot_be_modified(self):
        event = record_event(AuditEvent.Action.ADMIN_CHANGE, AuditEvent.Outcome.SUCCESS)
        event.outcome = AuditEvent.Outcome.FAILURE
        with self.assertRaises(ValueError):
            event.save()

    def test_audit_event_cannot_be_deleted(self):
        event = record_event(AuditEvent.Action.ADMIN_CHANGE, AuditEvent.Outcome.SUCCESS)
        with self.assertRaises(ValueError):
            event.delete()
        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())


class ProvenanceRecordModelTests(TestCase):
    def test_record_provenance_populates_fields(self):
        record = record_provenance(
            activity=ProvenanceRecord.Activity.ACQUIRED,
            description='Pulled from DHIS2 demo instance.',
            resource_type='RawDHIS2Record', resource_id=1,
            source_reference='dx=DX1 ou=OU1 pe=202508', performed_by='system:test',
        )
        self.assertEqual(record.activity, ProvenanceRecord.Activity.ACQUIRED)
        self.assertEqual(record.performed_by, 'system:test')
        self.assertTrue(record.correlation_id)

    def test_provenance_record_cannot_be_modified_or_deleted(self):
        record = record_provenance(
            activity=ProvenanceRecord.Activity.TRANSFORMED, description='x', performed_by='system:test',
        )
        record.description = 'changed'
        with self.assertRaises(ValueError):
            record.save()
        with self.assertRaises(ValueError):
            record.delete()


class AuthenticationAuditTests(RoleTestMixin, TestCase):
    """FR6.8: "Authentication attempts" - both outcomes."""

    def setUp(self):
        self.user = self.make_user(role=AUDITOR)
        self.user.set_password('correct-password')
        self.user.save()

    def test_successful_login_is_audited(self):
        response = APIClient().post(
            '/api/auth/token/', {'username': self.user.username, 'password': 'correct-password'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.filter(action=AuditEvent.Action.AUTHENTICATION).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.actor, self.user.username)

    def test_failed_login_is_audited(self):
        response = APIClient().post(
            '/api/auth/token/', {'username': self.user.username, 'password': 'wrong-password'}, format='json',
        )
        self.assertEqual(response.status_code, 401)
        event = AuditEvent.objects.filter(action=AuditEvent.Action.AUTHENTICATION).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.DENIED)


class AccessDeniedAuditTests(RoleTestMixin, TestCase):
    """FR6.8: "Access denied events" - both an authenticated-but-wrong-role
    403 and an anonymous 401 against a protected endpoint.
    """

    def test_permission_denied_is_audited(self):
        client = self.client_for(self.make_user(role=DATA_PROVIDER))
        response = client.get('/api/core/observations/')
        self.assertEqual(response.status_code, 403)
        event = AuditEvent.objects.filter(action=AuditEvent.Action.ACCESS_DENIED).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.DENIED)
        self.assertEqual(event.resource_type, 'ObservationViewSet')

    def test_anonymous_access_is_audited(self):
        response = APIClient().get('/api/core/observations/')
        self.assertEqual(response.status_code, 401)
        event = AuditEvent.objects.filter(action=AuditEvent.Action.AUTHENTICATION).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.DENIED)
        self.assertEqual(event.actor, 'anonymous')


class DatasetViewAndDownloadAuditTests(RoleTestMixin, TestCase):
    """FR6.8: "Dataset viewing" and "Dataset downloading"."""

    def setUp(self):
        self.district = District.objects.create(dhis2_org_unit_uid='OU_BO', name='Bo')
        self.indicator = Indicator.objects.create(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        raw = RawDHIS2Record.objects.create(
            dx_uid='DX_ANC1', dx_name='ANC 1st visit', org_unit_uid='OU_BO', org_unit_name='Bo',
            period='202508', value='10', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        Observation.objects.create(
            indicator=self.indicator, district=self.district, period='202508', value=10.0, source_raw_record=raw,
        )
        self.product = DataProduct.objects.create(title='ANC product', indicator=self.indicator)

    def test_listing_observations_logs_dataset_view(self):
        client = self.client_for(self.make_user(role=AUDITOR))
        response = client.get('/api/core/observations/')
        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.filter(action=AuditEvent.Action.DATASET_VIEW).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.resource_type, 'Observation')

    def test_downloading_data_product_logs_dataset_download(self):
        client = self.client_for(self.make_user(role=ANALYST))
        response = client.get(f'/api/core/data-products/{self.product.id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        event = AuditEvent.objects.filter(action=AuditEvent.Action.DATASET_DOWNLOAD).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.resource_type, 'DataProduct')
        self.assertEqual(event.resource_id, str(self.product.id))

    def test_data_provider_cannot_download_observation_values(self):
        """Downloading exposes real Observation values, which
        data_provider cannot read anywhere else in this API (see
        docs/rbac.md) - the download action must not be more permissive
        than ObservationViewSet itself, even though DataProductViewSet's
        list/retrieve routes are open to data_provider.
        """
        client = self.client_for(self.make_user(role=DATA_PROVIDER))
        response = client.get(f'/api/core/data-products/{self.product.id}/download/')
        self.assertEqual(response.status_code, 403)


class PipelineAuditTests(TestCase):
    """FR6.8: "Data acquisition", "Data transformation", "Data validation"
    and "Dataset publication" are audited from the pipeline services
    themselves, not only from the API layer.
    """

    def setUp(self):
        District.objects.create(dhis2_org_unit_uid='OU_BO', name='Bo')

    def test_transform_raw_records_logs_data_transformation(self):
        RawDHIS2Record.objects.create(
            dx_uid='DX_ANC1', dx_name='ANC 1st visit', org_unit_uid='OU_BO', org_unit_name='Bo',
            period='202508', value='10', raw_payload={}, source_url='https://example.test/api/analytics',
        )
        transform_raw_records()
        event = AuditEvent.objects.filter(action=AuditEvent.Action.DATA_TRANSFORMATION).latest('timestamp')
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)

    def test_sync_data_product_records_provenance(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        product = sync_data_product(indicator)
        record = ProvenanceRecord.objects.filter(data_product=product).latest('occurred_at')
        self.assertEqual(record.activity, ProvenanceRecord.Activity.TRANSFORMED)

    def test_run_quality_checks_logs_validation_and_publication(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_ANC1', name='ANC 1st visit')
        product = DataProduct.objects.create(title='x', indicator=indicator)
        run_quality_checks(product)

        validation = AuditEvent.objects.filter(action=AuditEvent.Action.DATA_VALIDATION).latest('timestamp')
        self.assertEqual(validation.resource_id, str(product.id))

        publication = AuditEvent.objects.filter(action=AuditEvent.Action.DATASET_PUBLICATION).latest('timestamp')
        # No observations and governance not reviewed -> blocked -> denied.
        self.assertEqual(publication.outcome, AuditEvent.Outcome.DENIED)
