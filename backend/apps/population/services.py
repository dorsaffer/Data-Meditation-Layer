"""CSV ingestion, district reconciliation, and the derived UHC service-
coverage metric. Deliberately imports only from apps.data_products
(District, Indicator, Observation) - never apps.dhis2 or its client -
so this integration stays independent of the DHIS2-specific acquisition
layer, exactly like apps.fhir.builders already does.
"""
from __future__ import annotations

import csv
import logging

from apps.data_products.models import District, Indicator, Observation

from .models import DistrictPopulation, DistrictPopulationMapping, PopulationDataQualityIssue, RawPopulationRecord

logger = logging.getLogger(__name__)

SERVICE_COVERAGE_CAVEAT = (
    'This ratio is a potential indicator of relatively low reported service activity, not a '
    'definitive statement about healthcare access. Service-reporting completeness, population '
    'estimate accuracy, and other contextual factors can all affect the result.'
)


def import_population_csv(path: str, reference_year: int = 2021) -> dict:
    """Reads the source census CSV and upserts RawPopulationRecord rows.
    A re-import that disagrees with an existing row's total is treated
    as a conflict to review, not silently overwritten - the existing
    value is kept and a duplicate_record issue is recorded.
    """
    created = 0
    updated = 0
    conflicts = 0

    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            district_name = row['district'].strip()
            total = int(row['total'])
            male = int(row['male'])
            female = int(row['female'])

            existing = RawPopulationRecord.objects.filter(
                district_name=district_name, reference_year=reference_year,
            ).first()
            if existing and existing.total != total:
                PopulationDataQualityIssue.objects.create(
                    issue_type=PopulationDataQualityIssue.IssueType.DUPLICATE_RECORD,
                    district_name=district_name,
                    detail=(
                        f'Re-import for {district_name} ({reference_year}) reports total={total}, '
                        f'which differs from the already-stored total={existing.total}. Kept the '
                        f'existing value; review and resolve manually before re-running import.'
                    ),
                )
                conflicts += 1
                continue

            _record, was_created = RawPopulationRecord.objects.update_or_create(
                district_name=district_name, reference_year=reference_year,
                defaults={
                    'region': row['region'].strip(),
                    'male': male,
                    'female': female,
                    'total': total,
                    'sex_ratio': float(row['sex_ratio']),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return {'created': created, 'updated': updated, 'conflicts': conflicts}


def _dhis2_name_for(mapping: DistrictPopulationMapping) -> str:
    return mapping.dhis2_district_hint or mapping.population_district_name


def reconcile_population(reference_year: int = 2021, stale_after_years: int = 3) -> dict:
    """The deterministic join: RawPopulationRecord -> DistrictPopulation,
    driven entirely by DistrictPopulationMapping (no name-matching
    happens inline here - the mapping table is the single source of
    truth for how a source district resolves to a DHIS2 district, or
    doesn't).

    Idempotent: replaces the current PopulationDataQualityIssue set with
    a freshly computed one on every run (this is a live data-quality
    report reflecting current state, not an accumulating log), and
    upserts DistrictPopulation rather than duplicating rows.
    """
    PopulationDataQualityIssue.objects.all().delete()

    # Self-healing: the mapping migration seeds exact/aggregate rows by
    # District *name* and tolerates the District not existing yet (a
    # fresh DB migrates before fetch_dhis2_data ever runs). If a mapping
    # meant to resolve is still unlinked, try again now that Districts
    # may have since been fetched - keeps this correct regardless of
    # migrate-vs-fetch ordering, without a manual admin fix-up step.
    for mapping in DistrictPopulationMapping.objects.filter(
        dhis2_district__isnull=True,
    ).exclude(match_type=DistrictPopulationMapping.MatchType.UNMATCHED):
        district = District.objects.filter(name=_dhis2_name_for(mapping)).first()
        if district:
            mapping.dhis2_district = district
            mapping.save(update_fields=['dhis2_district'])

    raw_records = RawPopulationRecord.objects.filter(reference_year=reference_year)
    mappings = {
        m.population_district_name: m
        for m in DistrictPopulationMapping.objects.select_related('dhis2_district')
    }

    totals: dict[int, int] = {}
    counts: dict[int, int] = {}

    for record in raw_records:
        if record.male + record.female != record.total:
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.CONFLICTING_IDENTIFIER,
                district_name=record.district_name,
                detail=(
                    f'{record.district_name}: male ({record.male}) + female ({record.female}) = '
                    f'{record.male + record.female}, which does not equal the reported total '
                    f'({record.total}).'
                ),
            )

        mapping = mappings.get(record.district_name)
        if mapping is None:
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.UNKNOWN_DISTRICT,
                district_name=record.district_name,
                detail=(
                    f'"{record.district_name}" has no entry in DistrictPopulationMapping - add one '
                    f'(exact/aggregate/unmatched) before it can be reconciled. Excluded from '
                    f'DistrictPopulation and from analytical calculations.'
                ),
            )
            continue

        if mapping.dhis2_district_id is None:
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.UNKNOWN_DISTRICT,
                district_name=record.district_name,
                detail=(
                    f'"{record.district_name}" is documented as unmatched: '
                    f'{mapping.notes or "no DHIS2 counterpart"}. Excluded from DistrictPopulation '
                    f'and from analytical calculations.'
                ),
            )
            continue

        totals[mapping.dhis2_district_id] = totals.get(mapping.dhis2_district_id, 0) + record.total
        counts[mapping.dhis2_district_id] = counts.get(mapping.dhis2_district_id, 0) + 1

    for district_id, total in totals.items():
        DistrictPopulation.objects.update_or_create(
            district_id=district_id, reference_year=reference_year,
            defaults={'total_population': total, 'source_record_count': counts[district_id]},
        )

    reconciled_district_ids = set(totals.keys())
    for district in District.objects.exclude(id__in=reconciled_district_ids):
        PopulationDataQualityIssue.objects.create(
            issue_type=PopulationDataQualityIssue.IssueType.MISSING_POPULATION,
            district_name=district.name,
            detail=(
                f'No population figure resolves to DHIS2 district "{district.name}" for reference '
                f'year {reference_year}.'
            ),
        )

    for district_id in reconciled_district_ids:
        if not Observation.objects.filter(district_id=district_id).exists():
            district_name = District.objects.get(id=district_id).name
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.MISSING_DHIS2_OBSERVATION,
                district_name=district_name,
                detail=(
                    f'District "{district_name}" has a reconciled population but no DHIS2 '
                    f'observations at all.'
                ),
            )

    periods = list(Observation.objects.values_list('period', flat=True))
    if periods:
        earliest_year = int(min(periods)[:4])
        latest_year = int(max(periods)[:4])

        if reference_year < earliest_year or reference_year > latest_year:
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.OUT_OF_PERIOD,
                detail=(
                    f'Population reference year {reference_year} falls outside the DHIS2 '
                    f'observation period range ({earliest_year}-{latest_year}).'
                ),
            )

        if latest_year - reference_year > stale_after_years:
            PopulationDataQualityIssue.objects.create(
                issue_type=PopulationDataQualityIssue.IssueType.STALE_DATA,
                detail=(
                    f'Population reference year {reference_year} is {latest_year - reference_year} '
                    f'years older than the most recent DHIS2 observation period ({latest_year}); '
                    f'consider refreshing from a newer census/estimate.'
                ),
            )

    return {
        'districts_reconciled': len(reconciled_district_ids),
        'issues': PopulationDataQualityIssue.objects.count(),
    }


def compute_service_coverage(
    indicator_dx_uid: str | None = None, period: str | None = None, reference_year: int | None = None,
) -> dict:
    """Service Activity Ratio = reported service activity / population,
    per DHIS2 district. A district missing either side is returned with
    excluded=True and a reason - never silently dropped. Flags the
    bottom 25% (at least 1) of comparable districts by ratio as
    potentially_underserved: a signal for follow-up, not a diagnosis -
    `caveat` in the return value must always accompany the result
    wherever it's surfaced.
    """
    indicator = (
        Indicator.objects.filter(dhis2_dx_uid=indicator_dx_uid).first()
        if indicator_dx_uid else Indicator.objects.first()
    )
    if indicator is None:
        return {
            'indicator': None, 'period': period, 'reference_year': reference_year,
            'rows': [], 'caveat': SERVICE_COVERAGE_CAVEAT,
        }

    if period is None:
        period = (
            Observation.objects.filter(indicator=indicator)
            .order_by('-period').values_list('period', flat=True).first()
        )
    if reference_year is None:
        reference_year = (
            DistrictPopulation.objects.order_by('-reference_year')
            .values_list('reference_year', flat=True).first()
        )

    populations = {
        dp.district_id: dp for dp in DistrictPopulation.objects.filter(reference_year=reference_year)
    } if reference_year else {}
    observations = {
        obs.district_id: obs for obs in Observation.objects.filter(indicator=indicator, period=period)
    } if period else {}

    rows = []
    for district in District.objects.all():
        population = populations.get(district.id)
        observation = observations.get(district.id)
        excluded = population is None or observation is None
        row = {
            'district_id': district.id,
            'district': district.name,
            'population': population.total_population if population else None,
            'service_activity': observation.value if observation else None,
            'ratio_percent': None,
            'excluded': excluded,
            'excluded_reason': '',
            'potentially_underserved': False,
        }
        if excluded:
            reasons = []
            if population is None:
                reasons.append('no reconciled population for this reference year')
            if observation is None:
                reasons.append('no DHIS2 observation for this indicator/period')
            row['excluded_reason'] = '; '.join(reasons)
        else:
            row['ratio_percent'] = round((observation.value / population.total_population) * 100, 2)
        rows.append(row)

    comparable = sorted((row for row in rows if not row['excluded']), key=lambda row: row['ratio_percent'])
    underserved_count = max(1, round(len(comparable) * 0.25)) if comparable else 0
    for row in comparable[:underserved_count]:
        row['potentially_underserved'] = True

    return {
        'indicator': indicator.name,
        'period': period,
        'reference_year': reference_year,
        'rows': rows,
        'caveat': SERVICE_COVERAGE_CAVEAT,
    }
