"""FR2: RawDHIS2Record -> canonical model, and DataProduct governance sync.

transform_raw_records() is pure transformation logic — no HTTP.
Idempotent: safe to re-run against the same raw records without
creating duplicate Observations.

sync_data_product() is deliberately the only writer of the
pipeline-derived DataProduct fields (refresh_date, temporal_coverage_*,
transformation_status, quality_status). It never touches the
governance judgement fields (sensitivity_classification,
permitted_audience, title, purpose, data_owner, source,
geographic_coverage, schema_version) once a DataProduct exists — those
are set once at creation (to conservative defaults) and from then on
are only ever changed by a human through the admin form.

Design note: sync_data_product is called only from
transform_to_canonical, not from fetch_dhis2_data. Acquisition
(apps.dhis2) intentionally knows nothing about the canonical model or
DataProduct - keeping FR1's "separate source-specific extraction from
downstream transformation" requirement intact. refresh_date is still
accurate regardless of when fetch ran, because it's read directly from
RawDHIS2Record here.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.data_products.models import DataProduct, District, Indicator, Observation
from apps.dhis2.models import RawDHIS2Record

logger = logging.getLogger(__name__)


def transform_raw_records() -> dict:
    created = 0
    updated = 0
    skipped = 0
    touched_indicator_ids = set()

    for raw in RawDHIS2Record.objects.all():
        try:
            value = float(raw.value)
        except (TypeError, ValueError):
            logger.warning(
                'Skipping non-numeric value for dx=%s ou=%s pe=%s: %r',
                raw.dx_uid, raw.org_unit_uid, raw.period, raw.value,
            )
            skipped += 1
            continue

        district, _ = District.objects.get_or_create(
            dhis2_org_unit_uid=raw.org_unit_uid,
            defaults={'name': raw.org_unit_name},
        )
        indicator, _ = Indicator.objects.get_or_create(
            dhis2_dx_uid=raw.dx_uid,
            defaults={'name': raw.dx_name},
        )
        touched_indicator_ids.add(indicator.id)

        _obs, obs_created = Observation.objects.update_or_create(
            indicator=indicator,
            district=district,
            period=raw.period,
            defaults={'value': value, 'source_raw_record': raw},
        )
        if obs_created:
            created += 1
        else:
            updated += 1

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'indicator_ids': touched_indicator_ids,
    }


def sync_data_product(indicator: Indicator) -> DataProduct:
    product, _created = DataProduct.objects.get_or_create(
        indicator=indicator,
        defaults={
            'title': f'{indicator.name} — District Level, Sierra Leone',
            'purpose': f'Supports Universal Health Coverage analysis of {indicator.name} by district.',
            'data_owner': 'Ministry of Health — HMIS Unit',
            'source': f'DHIS2 Sierra Leone demo instance ({settings.DHIS2_BASE_URL})',
            'geographic_coverage': 'Sierra Leone — all districts',
            'schema_version': '1.0',
            'sensitivity_classification': DataProduct.SensitivityClassification.RESTRICTED,
            'permitted_audience': ['admin'],
        },
    )

    observations = Observation.objects.filter(indicator=indicator)
    periods = list(observations.values_list('period', flat=True))
    if periods:
        product.temporal_coverage_start = min(periods)
        product.temporal_coverage_end = max(periods)

    latest_raw = (
        RawDHIS2Record.objects.filter(dx_uid=indicator.dhis2_dx_uid).order_by('-fetched_at').first()
    )
    if latest_raw:
        product.refresh_date = latest_raw.fetched_at

    product.transformation_status = (
        DataProduct.TransformationStatus.CANONICAL
        if observations.exists()
        else DataProduct.TransformationStatus.RAW_ONLY
    )
    # quality_status is left alone here: no quality screening exists yet
    # (a later phase sets it to passed/flagged based on QualityFlags).

    product.save()
    return product
