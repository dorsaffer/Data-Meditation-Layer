"""District population data, integrated with DHIS2 service-activity data
to support Universal Health Coverage (UHC) analysis - see docs/
population-integration.md for the full rationale, the district
reconciliation table, and the data-quality taxonomy.

Mirrors this codebase's established raw-ingestion -> canonical-transform
split (apps.dhis2 -> apps.data_products): RawPopulationRecord is the
unmodified anchor (one row per source CSV line), DistrictPopulation is
the canonical, reconciled result joined to apps.data_products.District.
The only difference from the DHIS2 pipeline is the "external system" is
a static census CSV, not an HTTP API - so there is no client/acquisition
module here, only a CSV reader in services.py.

DistrictPopulationMapping is deliberately its own model, not inline
join logic: the geographic identifier mapping must be "documented and
maintained separately from the source data" (explicit requirement), so
it lives in its own admin-editable table, seeded once by a data
migration with the real 16-row reconciliation.
"""
from django.db import models

from apps.data_products.models import District


class RawPopulationRecord(models.Model):
    """One unmodified row from the source census CSV. Never edited
    directly - only added/refreshed via import_population_csv's
    update_or_create on (district_name, reference_year).
    """

    region = models.CharField(max_length=100)
    district_name = models.CharField(max_length=100, help_text="District name exactly as it appears in the source.")
    male = models.PositiveIntegerField()
    female = models.PositiveIntegerField()
    total = models.PositiveIntegerField()
    sex_ratio = models.FloatField()
    reference_year = models.PositiveSmallIntegerField(default=2021)
    source_document = models.CharField(
        max_length=255,
        default='Statistics Sierra Leone - 2021 Mid-Term Population and Housing Census, Final Results by District (2022-09-22)',
    )
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['district_name', 'reference_year'],
                name='unique_population_record_district_year',
            )
        ]
        ordering = ['region', 'district_name']

    def __str__(self):
        return f'{self.district_name} ({self.reference_year}) = {self.total}'


class DistrictPopulationMapping(models.Model):
    """The explicit, human-maintained geographic identifier mapping
    between population-dataset district names and DHIS2 districts.
    Seeded by migrations/0002_seed_district_mapping.py with the real
    16-row reconciliation (12 exact, 2 rows aggregating into "Western
    Area", 2 unmatched - see docs/population-integration.md). Editable
    via the admin, same "governance judgement, human-maintained" pattern
    as DataProduct's judgement fields.
    """

    class MatchType(models.TextChoices):
        EXACT = 'exact', 'Exact name match'
        AGGREGATE = 'aggregate', 'Aggregated into a DHIS2 district'
        UNMATCHED = 'unmatched', 'No DHIS2 counterpart'

    population_district_name = models.CharField(max_length=100, unique=True)
    dhis2_district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, blank=True, related_name='population_mappings',
        help_text='Null means either deliberately unmatched (see notes), or not yet resolved because '
                   'this District did not exist when the mapping was seeded - see dhis2_district_hint.',
    )
    dhis2_district_hint = models.CharField(
        max_length=100, blank=True, default='',
        help_text='District name to (re-)resolve dhis2_district against if it is still null - e.g. '
                   'on a fresh DB migrated before fetch_dhis2_data has ever run. Defaults to '
                   'population_district_name when blank; only needs to differ for an aggregate '
                   'match (e.g. "Western Area" for the West Rural/West Urban rows). Unused for '
                   'match_type=unmatched.',
    )
    match_type = models.CharField(max_length=20, choices=MatchType.choices)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['population_district_name']

    def __str__(self):
        target = self.dhis2_district.name if self.dhis2_district else 'UNMATCHED'
        return f'{self.population_district_name} -> {target} ({self.match_type})'


class DistrictPopulation(models.Model):
    """Canonical, reconciled population per DHIS2 district - the join
    target for analytical comparisons against Observation values.
    source_record_count > 1 means multiple population rows were
    aggregated into this one DHIS2 district (see the Western Area case).
    """

    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='populations')
    total_population = models.PositiveIntegerField()
    reference_year = models.PositiveSmallIntegerField()
    source_record_count = models.PositiveSmallIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['district', 'reference_year'],
                name='unique_district_population_year',
            )
        ]
        ordering = ['district__name']

    def __str__(self):
        return f'{self.district.name} ({self.reference_year}) = {self.total_population}'


class PopulationDataQualityIssue(models.Model):
    """The data-quality report required by the integration: every issue
    type named in the acceptance criteria maps to exactly one of these
    choices and one code path in services.reconcile_population(). Never
    silently dropped - a record that can't be reliably joined shows up
    here instead of just vanishing from DistrictPopulation.
    """

    class IssueType(models.TextChoices):
        MISSING_POPULATION = 'missing_population', 'Missing population value'
        MISSING_DHIS2_OBSERVATION = 'missing_dhis2_observation', 'Missing DHIS2 observation'
        UNKNOWN_DISTRICT = 'unknown_district', 'Unknown/unmatched district'
        DUPLICATE_RECORD = 'duplicate_record', 'Duplicate district record'
        CONFLICTING_IDENTIFIER = 'conflicting_identifier', 'Conflicting district identifier or figures'
        OUT_OF_PERIOD = 'out_of_period', 'Population data outside the reporting period'
        STALE_DATA = 'stale_data', 'Stale/outdated population data'

    issue_type = models.CharField(max_length=30, choices=IssueType.choices)
    district_name = models.CharField(max_length=100, blank=True, default='')
    detail = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detected_at']

    def __str__(self):
        return f'{self.get_issue_type_display()}: {self.district_name or "(n/a)"}'
