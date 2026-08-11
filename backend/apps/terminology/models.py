"""FR6.4: DHIS2 data element / local concept -> recognised terminology
mapping, as an explicit, reviewable record independent of the DHIS2
acquisition connector (apps.dhis2) and the canonical model
(apps.data_products).

source_code deliberately stores the source system's own identifier
(e.g. Indicator.dhis2_dx_uid) as a plain string rather than a
ForeignKey to Indicator: mappings must be creatable/updatable without
touching the ingestion app, and a "local concept" mapping may have no
Indicator row at all. apps.fhir.builders resolves the link at export
time via TerminologyMapping.objects.filter(source_code=...).

Status lifecycle (see apps/terminology/services.py, the only place
that is allowed to change status):
  PROPOSED -> ACCEPTED   (human review only, via review_mapping())
  PROPOSED -> REJECTED   (human review only, via review_mapping())
  (none)   -> UNMAPPED   (explicit "no appropriate code exists" decision,
                          via mark_unmapped() - never assigned an
                          inaccurate code just to fill the field)
propose_mapping() - the only path automated/AI-assisted semantic
matching may use - can only ever create PROPOSED rows. Nothing in this
app can move a mapping to ACCEPTED without a reviewer.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q


class TerminologyMapping(models.Model):
    class Status(models.TextChoices):
        PROPOSED = 'proposed', 'Proposed'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        UNMAPPED = 'unmapped', 'Unmapped'

    class Terminology(models.TextChoices):
        ICD_10 = 'icd10', 'ICD-10'
        ICD_11 = 'icd11', 'ICD-11'
        LOINC = 'loinc', 'LOINC'
        SNOMED_CT = 'snomed_ct', 'SNOMED CT'
        OTHER = 'other', 'Other'

    class MappingMethod(models.TextChoices):
        MANUAL = 'manual', 'Manual (entered by a data steward)'
        SEMANTIC_SEARCH = 'semantic_search', 'Semantic search (heuristic text match, AI-assisted)'

    # --- source (DHIS2 data element or local concept) ---
    source_system = models.CharField(
        max_length=100, default='DHIS2',
        help_text='e.g. "DHIS2" or "LOCAL" for a concept with no DHIS2 origin.',
    )
    source_code = models.CharField(
        max_length=100,
        help_text='The source system\'s own identifier, e.g. Indicator.dhis2_dx_uid.',
    )
    source_display = models.CharField(max_length=255, help_text='Source concept/name, e.g. "Malaria cases".')

    # --- target (recognised terminology / controlled code system) ---
    # blank for UNMAPPED rows: an explicit "no target exists" decision,
    # not an unset field.
    target_terminology = models.CharField(max_length=20, choices=Terminology.choices, blank=True, default='')
    target_code = models.CharField(max_length=50, blank=True, default='')
    target_display = models.CharField(max_length=255, blank=True, default='')
    terminology_version = models.CharField(
        max_length=50, blank=True, default='',
        help_text='The exact terminology release used, e.g. "ICD-10 2019" - required for reproducibility.',
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    mapping_method = models.CharField(max_length=20, choices=MappingMethod.choices, default=MappingMethod.MANUAL)
    confidence = models.FloatField(
        null=True, blank=True,
        help_text='Similarity score from an automated/semantic proposal. Never set for manual mappings.',
    )
    rationale = models.TextField(help_text='Why this target code was proposed/accepted/rejected.')

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='terminology_mapping_reviews',
        help_text='Set only by human review (apps.terminology.services.review_mapping) - never by automation.',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_system', 'source_code', '-created_at']
        constraints = [
            # At most one ACCEPTED mapping per (source, target terminology) -
            # the FHIR pipeline must never face an ambiguous "which accepted
            # code do I use" choice. Multiple PROPOSED/REJECTED rows for the
            # same source+terminology stay allowed, preserving review history.
            models.UniqueConstraint(
                fields=['source_system', 'source_code', 'target_terminology'],
                condition=Q(status='accepted'),
                name='unique_accepted_mapping_per_source_and_terminology',
            ),
        ]

    def __str__(self):
        target = f'{self.target_terminology}:{self.target_code}' if self.target_code else 'UNMAPPED'
        return f'{self.source_system}:{self.source_code} -> {target} ({self.status})'
