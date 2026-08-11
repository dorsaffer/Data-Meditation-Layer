"""canonical model (District/Indicator/Observation) -> real HL7
FHIR R4 resources, as plain JSON-serialisable dicts.

Resource choices and why (see also apps/fhir/services.py for how they're
validated):

- Organization (one, shared): the data steward already tracked as
  DataProduct.data_owner - reused, not duplicated.
- Location (one per District, plus one country-level parent): a
  district is a jurisdictional geographic area, not a treating
  facility, hence physicalType=jdn (jurisdiction) and no
  managingOrganization - that field would wrongly imply a health
  facility operates there.
- Measure (one per Indicator): defines *what* is measured
  (population-level, scoring=continuous-variable), matching
  Indicator's role in the canonical model.
- MeasureReport (one per Observation): type=summary because DHIS2
  analytics data is aggregate with no patient identity - this is the
  key semantic choice that keeps this pipeline clear of individual-level
  clinical resources entirely.
- Bundle (type=collection, one per Indicator export): groups everything
  above for one indicator's export/validation run. `collection` rather
  than `transaction`/`document` since nothing is being persisted to a
  remote FHIR store here and no single resource is asserting document
  authorship - an implementation assumption, not a spec requirement.
- Provenance (one per Bundle): extends the traceability chain the
  RawDHIS2Record model already documents ("the traceability anchor
  everything downstream points back to") into FHIR, pointing every
  MeasureReport back at the exact raw DHIS2 rows it was built from.

Plain dicts rather than a typed resource-model library are used
deliberately: the pydantic-v2-native releases of the `fhir.resources`
package only ship R4B/R5, and the true-R4 releases require a legacy
pydantic v1 stack (verified broken under pydantic v2 - Measure built
with zero fields). The actual conformity authority is the self-hosted
HAPI FHIR R4 server's $validate operation (apps/fhir/services.py), not
a client-side library, so this doesn't weaken the conformity claim.

FHIR release: R4. No implementation assumption beyond what's noted
above and in each builder's docstring.
"""
from __future__ import annotations

import calendar
import re
import uuid
from datetime import date

from django.utils import timezone

CANONICAL_BASE = 'https://data-mediation.sl.gov/fhir'
ORGANIZATION_ID = 'moh-hmis-unit'
COUNTRY_LOCATION_ID = 'country-sl'


def parse_dhis2_period(period: str) -> tuple[date, date]:
    """Convert a DHIS2 period string into a FHIR Period's start/end
    dates. Only monthly ("YYYYMM") and yearly ("YYYY") periods are
    supported - the only period types this pipeline currently requests
    (see fetch_dhis2_data's default --pe of LAST_12_MONTHS). Any other
    format raises rather than silently guessing, matching
    transform_raw_records' fail-loud-on-unexpected-shape style.
    """
    if len(period) == 6 and period.isdigit():
        year, month = int(period[:4]), int(period[4:6])
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if len(period) == 4 and period.isdigit():
        year = int(period)
        return date(year, 1, 1), date(year, 12, 31)
    raise ValueError(f'Unsupported DHIS2 period format: {period!r}')


def _fhir_name(text: str) -> str:
    """FHIR's `name` datatype (used for Measure.name) must match
    [A-Za-z]([A-Za-z0-9_]){0,254} - unlike `title`, it isn't free text.
    """
    slug = re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_') or 'measure'
    if not slug[0].isalpha():
        slug = f'measure_{slug}'
    return slug[:255]


def build_organization() -> dict:
    return {
        'resourceType': 'Organization',
        'id': ORGANIZATION_ID,
        'active': True,
        'name': 'Ministry of Health — Sierra Leone, HMIS Unit',
        'type': [{
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/organization-type',
                'code': 'govt',
                'display': 'Government',
            }],
        }],
    }


def build_country_location() -> dict:
    return {
        'resourceType': 'Location',
        'id': COUNTRY_LOCATION_ID,
        'status': 'active',
        'name': 'Sierra Leone',
        'mode': 'instance',
        'physicalType': {
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/location-physical-type',
                'code': 'jdn',
                'display': 'Jurisdiction',
            }],
        },
    }


def build_location(district) -> dict:
    return {
        'resourceType': 'Location',
        'id': f'district-{district.dhis2_org_unit_uid}',
        'identifier': [{'system': f'{CANONICAL_BASE}/identifiers/dhis2-org-unit', 'value': district.dhis2_org_unit_uid}],
        'status': 'active',
        'name': district.name,
        'mode': 'instance',
        'physicalType': {
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/location-physical-type',
                'code': 'jdn',
                'display': 'Jurisdiction',
            }],
        },
        'partOf': {'reference': f'Location/{COUNTRY_LOCATION_ID}'},
    }


def build_measure(indicator, codings: list[dict] | None = None) -> dict:
    """FR6.4: `codings` are pre-resolved FHIR Coding dicts for this
    indicator's *accepted* terminology mappings (see
    apps.terminology.services.get_accepted_codings, called by
    build_bundle) - passed in rather than looked up here so this
    builder stays DB-free like every other one in this module. Omitted
    entirely (no .group[].code) when nothing has been accepted yet,
    rather than guessing a code.
    """
    measure_id = f'measure-{indicator.dhis2_dx_uid}'
    measure = {
        'resourceType': 'Measure',
        'id': measure_id,
        'url': f'{CANONICAL_BASE}/Measure/{measure_id}',
        'identifier': [{'system': f'{CANONICAL_BASE}/identifiers/dhis2-data-element', 'value': indicator.dhis2_dx_uid}],
        'version': '1.0',
        'name': _fhir_name(indicator.name),
        'title': indicator.name,
        'status': 'active',
        'experimental': False,
        'publisher': 'Ministry of Health — Sierra Leone, HMIS Unit',
        'description': indicator.description or f'District-level {indicator.name}, Sierra Leone.',
        'scoring': {
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/measure-scoring',
                'code': 'continuous-variable',
                'display': 'Continuous Variable',
            }],
        },
    }
    if codings:
        measure['group'] = [{'code': {'coding': codings, 'text': indicator.name}}]
    return measure


def build_measure_report(observation, measure: dict) -> dict:
    """Small-cell suppression applies here too, not just to the
    analytics API - a MeasureReport is a publishable artefact in its own
    right. A disclosive count (< privacy.SMALL_CELL_THRESHOLD) is
    generalised to a FHIR Quantity with comparator='<', the standard
    FHIR way to express "less than this value" - the exact count never
    appears in the exported Bundle, but the report still carries a
    genuinely useful upper bound rather than being blanked out.
    """
    from apps.data_products.privacy import SMALL_CELL_THRESHOLD, is_small_cell

    start, end = parse_dhis2_period(observation.period)
    district = observation.district
    if is_small_cell(observation.value):
        measure_score = {'value': SMALL_CELL_THRESHOLD, 'comparator': '<'}
    else:
        measure_score = {'value': observation.value}
    group = {'measureScore': measure_score}
    # Mirrors Measure.group[].code when present, per FHIR MeasureReport
    # convention (the report's group should restate what the measure
    # definition it reports against was measuring).
    if measure.get('group') and measure['group'][0].get('code'):
        group['code'] = measure['group'][0]['code']
    return {
        'resourceType': 'MeasureReport',
        'id': f'measurereport-{observation.indicator.dhis2_dx_uid}-{district.dhis2_org_unit_uid}-{observation.period}',
        'status': 'complete',
        'type': 'summary',
        'measure': measure['url'],
        'subject': {'reference': f'Location/district-{district.dhis2_org_unit_uid}'},
        'date': timezone.now().isoformat(),
        'reporter': {'reference': f'Organization/{ORGANIZATION_ID}'},
        'period': {'start': start.isoformat(), 'end': end.isoformat()},
        'group': [group],
    }


def build_provenance(measure_reports: list[dict], raw_records) -> dict:
    """entity[].what deliberately uses Reference.identifier rather than
    Reference.reference: RawDHIS2Record isn't itself a FHIR resource, so
    there is no resource-typed URL to point at - identifier + display is
    the correct way to reference an external, non-FHIR source record.
    """
    return {
        'resourceType': 'Provenance',
        'id': f'provenance-{uuid.uuid4().hex[:12]}',
        'target': [{'reference': f'MeasureReport/{mr["id"]}'} for mr in measure_reports],
        'recorded': timezone.now().isoformat(),
        'activity': {
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/v3-DataOperation',
                'code': 'CREATE',
                'display': 'create',
            }],
        },
        'agent': [{
            'type': {
                'coding': [{
                    'system': 'http://terminology.hl7.org/CodeSystem/provenance-participant-type',
                    'code': 'assembler',
                    'display': 'Assembler',
                }],
            },
            'who': {'reference': f'Organization/{ORGANIZATION_ID}'},
        }],
        'entity': [{
            'role': 'source',
            'what': {
                'identifier': {
                    'system': raw.source_url,
                    'value': f'{raw.dx_uid}/{raw.org_unit_uid}/{raw.period}',
                },
                'display': f'DHIS2 raw analytics record (fetched {raw.fetched_at.isoformat()})',
            },
        } for raw in raw_records],
    }


def build_bundle(indicator) -> dict:
    """Assembles one Indicator's full FHIR export: Organization,
    country + district Locations, the Measure, one MeasureReport per
    Observation, and a Provenance tying it all back to the source
    RawDHIS2Record rows. Reads Observations from the DB but performs no
    writes and no HTTP - kept separate from services.py's
    validate/persist orchestration.

    FR6.4: also resolves this indicator's *accepted* terminology
    mappings (apps.terminology.services.get_accepted_codings) into the
    Measure/MeasureReport - a PROPOSED or REJECTED mapping is
    structurally invisible to this function, since get_accepted_codings
    only ever queries status=ACCEPTED rows.
    """
    from apps.data_products.models import Observation
    from apps.terminology.services import get_accepted_codings

    observations = (
        Observation.objects
        .filter(indicator=indicator)
        .select_related('district', 'source_raw_record')
    )

    organization = build_organization()
    country = build_country_location()
    codings = get_accepted_codings('DHIS2', indicator.dhis2_dx_uid)
    measure = build_measure(indicator, codings=codings)

    districts_by_uid = {}
    measure_reports = []
    raw_records = []
    for observation in observations:
        district = observation.district
        districts_by_uid[district.dhis2_org_unit_uid] = district
        measure_reports.append(build_measure_report(observation, measure))
        raw_records.append(observation.source_raw_record)

    locations = [build_location(d) for d in districts_by_uid.values()]
    # Provenance.target is required (1..*): omit the resource entirely
    # rather than emit one with an empty target when there's nothing yet
    # to trace - an indicator with zero Observations has nothing to
    # attest provenance for.
    provenance = [build_provenance(measure_reports, raw_records)] if measure_reports else []

    resources = [organization, country, *locations, measure, *measure_reports, *provenance]
    entries = [{'fullUrl': f'{CANONICAL_BASE}/{r["resourceType"]}/{r["id"]}', 'resource': r} for r in resources]

    return {
        'resourceType': 'Bundle',
        'type': 'collection',
        'timestamp': timezone.now().isoformat(),
        'identifier': {
            'system': f'{CANONICAL_BASE}/identifiers/export',
            'value': f'export-{indicator.dhis2_dx_uid}-{timezone.now().strftime("%Y%m%dT%H%M%S")}',
        },
        'entry': entries,
    }
