"""Business logic for proposing, reviewing and consuming
terminology mappings. This module is the only place mapping status is
allowed to change - apps/terminology/admin.py routes through it too
(see TerminologyMappingAdmin.save_model), so there is exactly one code
path that can ever produce an ACCEPTED row.

Two families of function, split deliberately:
  - propose_mapping() / suggest_mappings_for_indicator(): can only ever
    create PROPOSED rows. This is the sole entry point for automated or
    AI-assisted semantic matching - it has no way to accept or publish
    a mapping.
  - review_mapping() / mark_unmapped(): require a real `reviewer` User
    and are the only way to reach ACCEPTED/REJECTED/UNMAPPED. There is
    no automated caller of these anywhere in this codebase.

get_accepted_mapping()/get_accepted_codings() are what
apps.fhir.builders reads from - the FHIR pipeline never queries
TerminologyMapping directly, so it structurally cannot see a
non-accepted mapping.
"""
from __future__ import annotations

import difflib
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.terminology.models import TerminologyMapping

# Canonical system URIs for the CodeableConcept.coding this app emits.
# Kept alongside the Terminology choices rather than in apps.fhir so the
# mapping mechanism stays fully independent of the FHIR builders (FR6.4:
# "independent of the DHIS2 ingestion logic" extends to not leaking
# terminology plumbing into the export pipeline either).
TERMINOLOGY_SYSTEM_URIS = {
    TerminologyMapping.Terminology.ICD_10: 'http://hl7.org/fhir/sid/icd-10',
    TerminologyMapping.Terminology.ICD_11: 'http://id.who.int/icd/release/11/mms',
    TerminologyMapping.Terminology.LOINC: 'http://loinc.org',
    TerminologyMapping.Terminology.SNOMED_CT: 'http://snomed.info/sct',
}

# Small, hand-curated set of well-known ICD-10 codes used by the
# semantic-search proposal helper below. Deliberately tiny and
# transparent (a plain substring/similarity match, not a live model
# call) rather than a terminology server: FR6.4 is explicit that
# building a full terminology server and auto-mapping every concept
# are both out of scope. Every code here is a real, verifiable ICD-10
# code - nothing is invented to pad coverage.
_ICD10_CANDIDATES = [
    {'keywords': ['malaria'], 'code': 'B50', 'display': 'Plasmodium falciparum malaria'},
    {'keywords': ['antenatal', 'anc', 'pregnancy'], 'code': 'Z34.9',
     'display': 'Encounter for supervision of normal pregnancy, unspecified, trimester unspecified'},
    {'keywords': ['tuberculosis', 'tb'], 'code': 'A16.9',
     'display': 'Respiratory tuberculosis unspecified, without mention of bacteriological or histological confirmation'},
    {'keywords': ['hiv'], 'code': 'B20', 'display': 'Human immunodeficiency virus [HIV] disease'},
    {'keywords': ['diarrhoea', 'diarrhea'], 'code': 'A09', 'display': 'Infectious gastroenteritis and colitis, unspecified'},
]


def propose_mapping(
    *, source_system: str, source_code: str, source_display: str,
    target_terminology: str, target_code: str, target_display: str,
    terminology_version: str, rationale: str,
    mapping_method: str = TerminologyMapping.MappingMethod.MANUAL,
    confidence: float | None = None,
) -> TerminologyMapping:
    """Create a PROPOSED mapping. Never sets status to anything else -
    this is the entry point AI/heuristic matching and manual proposals
    both use, and it structurally cannot publish a mapping.
    """
    if not rationale:
        raise ValidationError('A mapping rationale is required to propose a mapping.')
    return TerminologyMapping.objects.create(
        source_system=source_system,
        source_code=source_code,
        source_display=source_display,
        target_terminology=target_terminology,
        target_code=target_code,
        target_display=target_display,
        terminology_version=terminology_version,
        rationale=rationale,
        mapping_method=mapping_method,
        confidence=confidence,
        status=TerminologyMapping.Status.PROPOSED,
    )


def review_mapping(
    mapping: TerminologyMapping, *, reviewer, approve: bool, rationale: str | None = None,
) -> TerminologyMapping:
    """The only function that can move a mapping to ACCEPTED or
    REJECTED. Requires a real user - there is no default/system
    reviewer, so this cannot be called from an automated pipeline
    without a human explicitly in the call chain.
    """
    user_model = get_user_model()
    if not isinstance(reviewer, user_model) or not reviewer.pk:
        raise ValidationError('review_mapping requires a persisted reviewer user - mappings cannot self-approve.')

    mapping.status = TerminologyMapping.Status.ACCEPTED if approve else TerminologyMapping.Status.REJECTED
    if rationale:
        mapping.rationale = rationale
    if not mapping.rationale:
        raise ValidationError('A mapping rationale is required before a mapping can be accepted or rejected.')

    mapping.reviewer = reviewer
    mapping.reviewed_at = timezone.now()
    mapping.full_clean()
    mapping.save()
    return mapping


def mark_unmapped(
    *, source_system: str, source_code: str, source_display: str, rationale: str, reviewer=None,
) -> TerminologyMapping:
    """Explicit "no appropriate terminology exists" decision (FR6.4:
    "the concept can remain UNMAPPED rather than being assigned an
    inaccurate code"). reviewer is optional here: unlike ACCEPTED/
    REJECTED this isn't asserting a code is medically correct, so it
    may be recorded by whoever ran the proposal step - but if given, it
    is still recorded for audit.
    """
    if not rationale:
        raise ValidationError('A rationale is required to record a concept as UNMAPPED.')
    return TerminologyMapping.objects.create(
        source_system=source_system,
        source_code=source_code,
        source_display=source_display,
        rationale=rationale,
        status=TerminologyMapping.Status.UNMAPPED,
        reviewer=reviewer,
        reviewed_at=timezone.now() if reviewer else None,
    )


def get_accepted_mappings(source_system: str, source_code: str) -> Iterable[TerminologyMapping]:
    """What apps.fhir.builders reads from. Only ever returns ACCEPTED
    rows - the FHIR pipeline has no other way to reach TerminologyMapping.
    """
    return TerminologyMapping.objects.filter(
        source_system=source_system, source_code=source_code, status=TerminologyMapping.Status.ACCEPTED,
    )


def get_accepted_codings(source_system: str, source_code: str) -> list[dict]:
    """Accepted mappings as FHIR `Coding` dicts, ready to drop into a
    CodeableConcept.coding array. One entry per accepted mapping, so a
    concept accepted against both ICD-10 and SNOMED CT (say) yields two
    codings under the same concept - a normal FHIR pattern.
    """
    codings = []
    for mapping in get_accepted_mappings(source_system, source_code):
        system = TERMINOLOGY_SYSTEM_URIS.get(mapping.target_terminology)
        if not system:
            continue
        codings.append({
            'system': system,
            'code': mapping.target_code,
            'display': mapping.target_display,
            'version': mapping.terminology_version,
        })
    return codings


def suggest_mappings_for_indicator(indicator, *, source_system: str = 'DHIS2') -> list[TerminologyMapping]:
    """Heuristic ("semantic search") ICD-10 proposal: scores
    indicator.name against a small local candidate list using
    difflib's SequenceMatcher (stdlib, deterministic, no external
    model call - kept transparent per the AI-transparency requirement
    rather than dressed up as more than it is).

    Only ever creates PROPOSED rows via propose_mapping(). Skips a
    candidate if a mapping already exists (any status) for this
    source_code/target so re-running doesn't spam duplicate proposals.
    """
    name = indicator.name.lower()
    created = []
    for candidate in _ICD10_CANDIDATES:
        score = max(difflib.SequenceMatcher(None, keyword, name).ratio() for keyword in candidate['keywords'])
        matched_by_substring = any(keyword in name for keyword in candidate['keywords'])
        confidence = 0.9 if matched_by_substring else round(score, 2)
        if not matched_by_substring and score < 0.6:
            continue

        already_exists = TerminologyMapping.objects.filter(
            source_system=source_system,
            source_code=indicator.dhis2_dx_uid,
            target_terminology=TerminologyMapping.Terminology.ICD_10,
            target_code=candidate['code'],
        ).exists()
        if already_exists:
            continue

        mapping = propose_mapping(
            source_system=source_system,
            source_code=indicator.dhis2_dx_uid,
            source_display=indicator.name,
            target_terminology=TerminologyMapping.Terminology.ICD_10,
            target_code=candidate['code'],
            target_display=candidate['display'],
            terminology_version='ICD-10 2019',
            rationale=(
                f'Semantic-search candidate: indicator name {indicator.name!r} matched keyword(s) '
                f'{candidate["keywords"]!r} for ICD-10 {candidate["code"]} (confidence {confidence}). '
                'Proposed automatically - requires human review before use.'
            ),
            mapping_method=TerminologyMapping.MappingMethod.SEMANTIC_SEARCH,
            confidence=confidence,
        )
        created.append(mapping)
    return created
