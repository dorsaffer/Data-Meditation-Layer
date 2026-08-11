"""FR6.6: the visible data-quality assessment and publish/publish-with-
warnings/blocked decision. This is also where FR6.7's privacy checks are
run (apps.data_products.privacy.run_privacy_checks) - see that module's
docstring for why it shares this table and decision rather than keeping
a second one; `check_code` values from it are prefixed `privacy_` so
they stay identifiable in this list.

run_quality_checks(product) is the only writer of QualityCheckResult and
of DataProduct.quality_status - deliberately mirroring
apps.data_products.services.sync_data_product's "one function owns these
pipeline-derived fields" rule. It is idempotent: every call deletes and
recomputes this product's QualityCheckResult set from current state, the
same idempotent-recompute pattern already used by
apps.population.services.reconcile_population for
PopulationDataQualityIssue.

Two branches, because DataProduct covers two different shapes of thing
(see DataProduct.indicator's docstring):
  - an indicator-linked product (the common case) is checked directly
    against its own Observation/RawDHIS2Record rows.
  - the one multi-source, cross-indicator product (indicator is None -
    "UHC District Service Coverage", apps.population) has no
    Observation set of its own to check; its quality signal already
    exists as PopulationDataQualityIssue rows computed by
    reconcile_population(), so this rolls those up into the same
    QualityCheckResult shape instead of re-deriving them. This is the
    one place apps.data_products intentionally imports from
    apps.population - the exact exception DataProduct.indicator's
    docstring already calls out.

Every check is tagged with a `method` (deterministic/heuristic/
human_required) and a `severity` (info/warning/blocker) so a human
reading the result never has to guess how much to trust a "passed":
  - deterministic: a hard fact - a regex match, a count, a DB
    constraint. No judgement call, no false positives.
  - heuristic: a statistical judgement call (an outlier threshold) that
    can have false positives/negatives - flag for review, not proof.
  - human_required: never evaluated by code at all. Reads a decision a
    person already made (DataProduct.governance_reviewed) and fails
    closed until they make it.
"""
from __future__ import annotations

import re
from statistics import pstdev
from typing import Iterable

from django.utils import timezone

from apps.data_products.models import DataProduct, District, Observation, QualityCheckResult
from apps.data_products.privacy import run_privacy_checks
from apps.dhis2.models import RawDHIS2Record

DHIS2_PERIOD_RE = re.compile(r'^\d{4}(0[1-9]|1[0-2])?$')
DHIS2_UID_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]{10}$')

STALE_DATA_THRESHOLD_DAYS = 180
OUTLIER_Z_THRESHOLD = 3.0
MIN_COMPARABLE_DISTRICTS = 3

Method = QualityCheckResult.Method
Severity = QualityCheckResult.Severity


def _record(product: DataProduct, *, code: str, name: str, method: str, severity: str, passed: bool, detail: str):
    return QualityCheckResult.objects.create(
        data_product=product, check_code=code, check_name=name,
        method=method, severity=severity, passed=passed, detail=detail,
    )


def _truncate(items: Iterable[str], limit: int = 5) -> str:
    items = list(items)
    shown = ', '.join(items[:limit])
    if len(items) > limit:
        shown += f', … ({len(items) - limit} more)'
    return shown


def run_quality_checks(product: DataProduct) -> DataProduct:
    QualityCheckResult.objects.filter(data_product=product).delete()

    if product.indicator_id is not None:
        _run_indicator_checks(product)
    else:
        _run_population_rollup_checks(product)

    run_privacy_checks(product)
    _check_governance_review(product)
    _apply_decision(product)
    return product


# ---- indicator-linked branch --------------------------------------------

def _run_indicator_checks(product: DataProduct) -> None:
    indicator = product.indicator
    observations = Observation.objects.filter(indicator=indicator).select_related('district')
    raw_records = RawDHIS2Record.objects.filter(dx_uid=indicator.dhis2_dx_uid)

    _check_completeness(product, observations)
    _check_duplicate_records(product)
    _check_valid_period_format(product, observations, raw_records)
    _check_valid_identifier_format(product, indicator, raw_records)
    _check_impossible_values(product, observations)
    _check_suspicious_values(product, observations)
    _check_geographic_identifier_consistency(product, observations)
    _check_stale_data(product)


def _check_completeness(product, observations) -> None:
    periods = sorted(set(observations.values_list('period', flat=True)))
    districts_count = District.objects.count()
    expected = districts_count * len(periods)
    actual = observations.count()

    if actual == 0:
        _record(
            product, code='completeness', name='Completeness', method=Method.DETERMINISTIC,
            severity=Severity.BLOCKER, passed=False,
            detail='No observations exist for this indicator.',
        )
    elif actual < expected:
        _record(
            product, code='completeness', name='Completeness', method=Method.DETERMINISTIC,
            severity=Severity.WARNING, passed=False,
            detail=(
                f'{actual} of {expected} expected district×period observations present '
                f'({expected - actual} missing).'
            ),
        )
    else:
        _record(
            product, code='completeness', name='Completeness', method=Method.DETERMINISTIC,
            severity=Severity.INFO, passed=True,
            detail=f'All {expected} expected district×period observations present.',
        )


def _check_duplicate_records(product) -> None:
    _record(
        product, code='duplicate_records', name='Duplicate records', method=Method.DETERMINISTIC,
        severity=Severity.INFO, passed=True,
        detail=(
            'Structurally guaranteed: unique_observation_indicator_district_period and '
            'unique_dhis2_record_dx_ou_period prevent a duplicate (indicator/dx, district/org unit, '
            'period) row from ever existing in this schema.'
        ),
    )


def _check_valid_period_format(product, observations, raw_records) -> None:
    periods = set(observations.values_list('period', flat=True)) | set(raw_records.values_list('period', flat=True))
    invalid = sorted(p for p in periods if not DHIS2_PERIOD_RE.match(p))
    passed = not invalid
    _record(
        product, code='valid_period_format', name='Valid period format', method=Method.DETERMINISTIC,
        severity=Severity.BLOCKER, passed=passed,
        detail=(
            'All periods match the DHIS2 YYYY/YYYYMM format.' if passed
            else f'Periods not matching YYYY/YYYYMM: {_truncate(invalid)}.'
        ),
    )


def _check_valid_identifier_format(product, indicator, raw_records) -> None:
    org_unit_uids = sorted(set(raw_records.values_list('org_unit_uid', flat=True)))
    invalid_ou = [u for u in org_unit_uids if not DHIS2_UID_RE.match(u)]
    invalid_dx = [] if DHIS2_UID_RE.match(indicator.dhis2_dx_uid) else [indicator.dhis2_dx_uid]
    invalid = invalid_dx + invalid_ou
    passed = not invalid
    _record(
        product, code='valid_identifier_format', name='Valid identifier format', method=Method.DETERMINISTIC,
        severity=Severity.BLOCKER, passed=passed,
        detail=(
            'All dx/org-unit identifiers match the DHIS2 UID pattern.' if passed
            else f'Identifiers not matching the DHIS2 UID pattern: {_truncate(invalid)}.'
        ),
    )


def _check_impossible_values(product, observations) -> None:
    negative = list(
        observations.filter(value__lt=0).select_related('district').values_list('district__name', 'period', 'value')
    )
    passed = not negative
    _record(
        product, code='impossible_values', name='Impossible values', method=Method.DETERMINISTIC,
        severity=Severity.BLOCKER, passed=passed,
        detail=(
            'No negative observation values.' if passed
            else f'Negative values found: {_truncate(f"{d}/{p}={v}" for d, p, v in negative)}.'
        ),
    )


def _check_suspicious_values(product, observations) -> None:
    by_period: dict[str, list[tuple[str, float]]] = {}
    for district_name, period, value in observations.values_list('district__name', 'period', 'value'):
        by_period.setdefault(period, []).append((district_name, value))

    outliers = []
    evaluated_periods = 0
    for period, rows in by_period.items():
        values = [v for _, v in rows]
        if len(values) < MIN_COMPARABLE_DISTRICTS:
            continue
        evaluated_periods += 1
        mean_value = sum(values) / len(values)
        stdev = pstdev(values)
        if stdev == 0:
            continue
        for district_name, value in rows:
            z = (value - mean_value) / stdev
            if abs(z) > OUTLIER_Z_THRESHOLD:
                outliers.append(f'{district_name}/{period}={value} (z={z:.1f})')

    if evaluated_periods == 0:
        _record(
            product, code='suspicious_values', name='Suspicious values (outliers)', method=Method.HEURISTIC,
            severity=Severity.WARNING, passed=True,
            detail=f'Fewer than {MIN_COMPARABLE_DISTRICTS} comparable districts per period - not evaluated.',
        )
        return

    passed = not outliers
    _record(
        product, code='suspicious_values', name='Suspicious values (outliers)', method=Method.HEURISTIC,
        severity=Severity.WARNING, passed=passed,
        detail=(
            f'No values more than {OUTLIER_Z_THRESHOLD} standard deviations from their period mean.'
            if passed else
            f'Statistical outliers (|z| > {OUTLIER_Z_THRESHOLD}): {_truncate(outliers)}. Heuristic - '
            f'flagged for review, not proof of a data error.'
        ),
    )


def _check_geographic_identifier_consistency(product, observations) -> None:
    district_ids = observations.values_list('district_id', flat=True).distinct()
    name_to_uids: dict[str, set[str]] = {}
    for name, uid in District.objects.filter(id__in=district_ids).values_list('name', 'dhis2_org_unit_uid'):
        name_to_uids.setdefault(name, set()).add(uid)
    collisions = {name: uids for name, uids in name_to_uids.items() if len(uids) > 1}
    passed = not collisions
    _record(
        product, code='geographic_identifier_consistency', name='Geographic identifier consistency',
        method=Method.DETERMINISTIC, severity=Severity.BLOCKER, passed=passed,
        detail=(
            'Every district name maps to exactly one DHIS2 org unit UID.' if passed
            else f'District names mapping to more than one UID: {_truncate(collisions.keys())}.'
        ),
    )


def _check_stale_data(product) -> None:
    if product.refresh_date is None:
        _record(
            product, code='stale_data', name='Stale data', method=Method.DETERMINISTIC,
            severity=Severity.WARNING, passed=False, detail='No refresh_date recorded yet.',
        )
        return

    age_days = (timezone.now() - product.refresh_date).days
    passed = age_days <= STALE_DATA_THRESHOLD_DAYS
    _record(
        product, code='stale_data', name='Stale data', method=Method.DETERMINISTIC,
        severity=Severity.WARNING, passed=passed,
        detail=f'Last refreshed {age_days} day(s) ago (threshold: {STALE_DATA_THRESHOLD_DAYS} days).',
    )


# ---- multi-source (population-joined) rollup branch ---------------------

def _run_population_rollup_checks(product: DataProduct) -> None:
    # Deliberate: apps.data_products has no reconciliation logic of its
    # own for this product - apps.population.services.reconcile_population
    # already computed these issues. Re-deriving them here would just be
    # a second, divergence-prone copy of the same logic.
    from apps.population.models import PopulationDataQualityIssue

    IssueType = PopulationDataQualityIssue.IssueType
    issues = PopulationDataQualityIssue.objects.all()

    def count(*issue_types: str) -> int:
        return issues.filter(issue_type__in=issue_types).count()

    total_districts = District.objects.count()
    missing = count(IssueType.MISSING_POPULATION, IssueType.MISSING_DHIS2_OBSERVATION)
    _record(
        product, code='completeness', name='Completeness', method=Method.DETERMINISTIC,
        severity=Severity.BLOCKER if total_districts and missing >= total_districts else Severity.WARNING,
        passed=missing == 0,
        detail=(
            'All districts have a reconciled population and DHIS2 observations.' if missing == 0
            else f'{missing} district(s) missing a reconciled population or DHIS2 observation - see '
                 f'population data-quality issues.'
        ),
    )

    duplicate = count(IssueType.DUPLICATE_RECORD)
    _record(
        product, code='duplicate_records', name='Duplicate records', method=Method.DETERMINISTIC,
        severity=Severity.WARNING, passed=duplicate == 0,
        detail=(
            'No conflicting re-imports detected.' if duplicate == 0
            else f'{duplicate} conflicting re-import(s) detected and kept at their original value - '
                 f'see population data-quality issues.'
        ),
    )

    conflicting = count(IssueType.CONFLICTING_IDENTIFIER)
    _record(
        product, code='impossible_values', name='Impossible values', method=Method.DETERMINISTIC,
        severity=Severity.WARNING, passed=conflicting == 0,
        detail=(
            'male + female reconciles to total for every source row.' if conflicting == 0
            else f'{conflicting} source row(s) where male + female does not equal total - see '
                 f'population data-quality issues.'
        ),
    )

    unknown = count(IssueType.UNKNOWN_DISTRICT)
    _record(
        product, code='geographic_identifier_consistency', name='Geographic identifier consistency',
        method=Method.DETERMINISTIC, severity=Severity.WARNING, passed=unknown == 0,
        detail=(
            'Every source district resolves to a DHIS2 district.' if unknown == 0
            else f'{unknown} source district(s) have no DHIS2 counterpart and are excluded - see '
                 f'population data-quality issues.'
        ),
    )

    stale = count(IssueType.STALE_DATA, IssueType.OUT_OF_PERIOD)
    _record(
        product, code='stale_data', name='Stale data', method=Method.DETERMINISTIC,
        severity=Severity.WARNING, passed=stale == 0,
        detail=(
            'Population reference year is within range of current DHIS2 observation periods.'
            if stale == 0 else
            f'{stale} temporal-alignment issue(s) between the population reference year and DHIS2 '
            f'observation periods - see population data-quality issues.'
        ),
    )


# ---- shared: human-approval gate + decision ------------------------------

def _check_governance_review(product: DataProduct) -> None:
    _record(
        product, code='governance_review', name='Governance review', method=Method.HUMAN_REQUIRED,
        severity=Severity.BLOCKER, passed=product.governance_reviewed,
        detail=(
            'A data steward has confirmed sensitivity_classification and permitted_audience for this '
            'product.' if product.governance_reviewed else
            'A data steward must review sensitivity_classification and permitted_audience and mark '
            'this product governance_reviewed before it can be published. Not evaluated automatically '
            'by design.'
        ),
    )


def _apply_decision(product: DataProduct) -> None:
    checks = QualityCheckResult.objects.filter(data_product=product)
    failed = checks.filter(passed=False)

    if not checks.exists():
        decision = DataProduct.QualityStatus.UNSCREENED
    elif failed.filter(method=Method.HUMAN_REQUIRED).exists() or failed.filter(severity=Severity.BLOCKER).exists():
        decision = DataProduct.QualityStatus.BLOCKED
    elif failed.exists():
        decision = DataProduct.QualityStatus.PUBLISHABLE_WITH_WARNINGS
    else:
        decision = DataProduct.QualityStatus.PUBLISHABLE

    product.quality_status = decision
    product.save(update_fields=['quality_status'])
