from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from rest_framework.test import APIClient
from apps.accounts.permissions import ANALYST, AUDITOR, DATA_PROVIDER
from apps.accounts.test_utils import RoleTestMixin
from apps.data_products.models import Indicator
from apps.terminology.models import TerminologyMapping
from apps.terminology.services import (
    get_accepted_codings,
    get_accepted_mappings,
    mark_unmapped,
    propose_mapping,
    review_mapping,
    suggest_mappings_for_indicator,
)


def _propose(**overrides):
    defaults = dict(
        source_system='DHIS2', source_code='MALARIA_CASES', source_display='Malaria cases',
        target_terminology=TerminologyMapping.Terminology.ICD_10, target_code='B50',
        target_display='Plasmodium falciparum malaria', terminology_version='ICD-10 2019',
        rationale='Direct name match.',
    )
    defaults.update(overrides)
    return propose_mapping(**defaults)


class ProposeMappingTests(TestCase):
    """Proposing a mapping must never be able to publish it."""

    def test_propose_creates_proposed_status_with_no_reviewer(self):
        mapping = _propose()
        self.assertEqual(mapping.status, TerminologyMapping.Status.PROPOSED)
        self.assertIsNone(mapping.reviewer)
        self.assertIsNone(mapping.reviewed_at)

    def test_propose_requires_rationale(self):
        with self.assertRaises(ValidationError):
            _propose(rationale='')

    def test_propose_is_invisible_to_get_accepted_mappings(self):
        _propose()
        self.assertEqual(list(get_accepted_mappings('DHIS2', 'MALARIA_CASES')), [])
        self.assertEqual(get_accepted_codings('DHIS2', 'MALARIA_CASES'), [])


class ReviewMappingTests(TestCase):
    """Only review_mapping(), with a real reviewer, can accept or
    reject - this is the architectural guarantee that AI/automation can
    never self-approve a medical mapping.
    """

    def setUp(self):
        self.mapping = _propose()
        self.reviewer = get_user_model().objects.create_user(username='steward', password='x')

    def test_approve_sets_accepted_reviewer_and_timestamp(self):
        review_mapping(self.mapping, reviewer=self.reviewer, approve=True, rationale='Confirmed by data steward.')
        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.status, TerminologyMapping.Status.ACCEPTED)
        self.assertEqual(self.mapping.reviewer, self.reviewer)
        self.assertIsNotNone(self.mapping.reviewed_at)

    def test_reject_sets_rejected_and_reviewer(self):
        review_mapping(self.mapping, reviewer=self.reviewer, approve=False, rationale='Wrong code.')
        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.status, TerminologyMapping.Status.REJECTED)
        self.assertEqual(self.mapping.reviewer, self.reviewer)

    def test_requires_a_persisted_user_as_reviewer(self):
        unsaved_user = get_user_model()(username='ghost')
        with self.assertRaises(ValidationError):
            review_mapping(self.mapping, reviewer=unsaved_user, approve=True, rationale='x')

    def test_requires_a_rationale_to_accept(self):
        mapping = _propose(source_code='NO_RATIONALE', rationale='placeholder')
        mapping.rationale = ''
        with self.assertRaises(ValidationError):
            review_mapping(mapping, reviewer=self.reviewer, approve=True, rationale='')

    def test_accepted_mapping_is_now_visible_to_the_fhir_pipeline(self):
        review_mapping(self.mapping, reviewer=self.reviewer, approve=True, rationale='Confirmed.')
        codings = get_accepted_codings('DHIS2', 'MALARIA_CASES')
        self.assertEqual(codings, [{
            'system': 'http://hl7.org/fhir/sid/icd-10', 'code': 'B50',
            'display': 'Plasmodium falciparum malaria', 'version': 'ICD-10 2019',
        }])

    def test_only_one_accepted_mapping_per_source_and_terminology(self):
        review_mapping(self.mapping, reviewer=self.reviewer, approve=True, rationale='Confirmed.')
        competing = _propose(target_code='B54', target_display='Unspecified malaria')
        competing.status = TerminologyMapping.Status.ACCEPTED
        competing.reviewer = self.reviewer
        with self.assertRaises(IntegrityError), transaction.atomic():
            competing.save()


class MarkUnmappedTests(TestCase):
    def test_unmapped_requires_no_target_but_requires_rationale(self):
        mapping = mark_unmapped(
            source_system='DHIS2', source_code='UNKNOWN_CONCEPT', source_display='Unknown concept',
            rationale='No corresponding ICD-10 code exists.',
        )
        self.assertEqual(mapping.status, TerminologyMapping.Status.UNMAPPED)
        self.assertEqual(mapping.target_code, '')

    def test_unmapped_requires_rationale(self):
        with self.assertRaises(ValidationError):
            mark_unmapped(source_system='DHIS2', source_code='X', source_display='X', rationale='')


class SuggestMappingsForIndicatorTests(TestCase):
    """The 'semantic search' / AI-assisted path: heuristic, transparent,
    and only ever produces PROPOSED rows.
    """

    def test_matches_known_keyword_and_proposes_not_accepts(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_MALARIA', name='Malaria cases')
        proposed = suggest_mappings_for_indicator(indicator)
        self.assertEqual(len(proposed), 1)
        mapping = proposed[0]
        self.assertEqual(mapping.target_code, 'B50')
        self.assertEqual(mapping.status, TerminologyMapping.Status.PROPOSED)
        self.assertEqual(mapping.mapping_method, TerminologyMapping.MappingMethod.SEMANTIC_SEARCH)
        self.assertIsNotNone(mapping.confidence)

    def test_no_match_proposes_nothing(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_UNRELATED', name='Water pump functionality')
        self.assertEqual(suggest_mappings_for_indicator(indicator), [])

    def test_rerunning_does_not_duplicate_proposals(self):
        indicator = Indicator.objects.create(dhis2_dx_uid='DX_MALARIA', name='Malaria cases')
        suggest_mappings_for_indicator(indicator)
        second_run = suggest_mappings_for_indicator(indicator)
        self.assertEqual(second_run, [])
        self.assertEqual(TerminologyMapping.objects.filter(source_code='DX_MALARIA').count(), 1)


class AdminReviewWorkflowTests(TestCase):
    """Exercises the actual admin change form, not just the service
    functions directly - this is the "human review" surface a data
    steward really uses, so a form-field mismatch in save_model()
    would otherwise go unnoticed by the service-level tests above.
    """

    def setUp(self):
        self.mapping = _propose()
        self.steward = get_user_model().objects.create_superuser(
            username='steward-admin', password='x', email='steward@example.test',
        )
        self.client = Client()
        self.client.force_login(self.steward)

    def _form_data(self, **overrides):
        data = {
            'target_terminology': self.mapping.target_terminology,
            'target_code': self.mapping.target_code,
            'target_display': self.mapping.target_display,
            'terminology_version': self.mapping.terminology_version,
            'status': TerminologyMapping.Status.ACCEPTED,
            'rationale': 'Reviewed and confirmed via the admin form.',
        }
        data.update(overrides)
        return data

    def test_submitting_accepted_status_stamps_the_logged_in_reviewer(self):
        url = f'/admin/terminology/terminologymapping/{self.mapping.pk}/change/'
        response = self.client.post(url, self._form_data(), follow=True)
        self.assertEqual(response.status_code, 200)

        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.status, TerminologyMapping.Status.ACCEPTED)
        self.assertEqual(self.mapping.reviewer, self.steward)
        self.assertIsNotNone(self.mapping.reviewed_at)

    def test_editing_an_already_accepted_mapping_without_status_change_keeps_original_reviewer(self):
        other_reviewer = get_user_model().objects.create_user(username='other', password='x')
        review_mapping(self.mapping, reviewer=other_reviewer, approve=True, rationale='First review.')

        url = f'/admin/terminology/terminologymapping/{self.mapping.pk}/change/'
        self.client.post(url, self._form_data(target_display='Corrected display text'), follow=True)

        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.reviewer, other_reviewer)
        self.assertEqual(self.mapping.target_display, 'Corrected display text')


class TerminologyMappingViewSetPermissionTests(RoleTestMixin, TestCase):
    """analyst and auditor can read the mapping catalog (list, and the
    proposed/accepted actions); data_provider (and any unrecognized/
    no-role account) cannot.
    """

    def test_analyst_can_list(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/terminology-mappings/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_list(self):
        response = self.client_for(self.make_user(role=AUDITOR)).get('/api/core/terminology-mappings/')
        self.assertEqual(response.status_code, 200)

    def test_data_provider_cannot_list(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/terminology-mappings/')
        self.assertEqual(response.status_code, 403)

    def test_no_role_cannot_list(self):
        response = self.client_for(self.make_user()).get('/api/core/terminology-mappings/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list(self):
        response = APIClient().get('/api/core/terminology-mappings/')
        self.assertEqual(response.status_code, 401)

    def test_data_provider_cannot_read_proposed_action(self):
        response = self.client_for(self.make_user(role=DATA_PROVIDER)).get('/api/core/terminology-mappings/proposed/')
        self.assertEqual(response.status_code, 403)

    def test_analyst_can_read_accepted_action(self):
        response = self.client_for(self.make_user(role=ANALYST)).get('/api/core/terminology-mappings/accepted/')
        self.assertEqual(response.status_code, 200)

