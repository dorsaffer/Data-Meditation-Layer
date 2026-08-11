"""Seeds the explicit, human-reviewable geographic identifier mapping
between the 2021 census's 16 (post-2017) districts and this DHIS2
instance's 13 (pre-2017) districts - see docs/population-integration.md
for the full rationale.

Deliberately tolerant of District not existing yet: on a fresh DB,
migrations run before fetch_dhis2_data/transform_to_canonical ever
have, so District may be empty here. dhis2_district is left null in
that case (never a crash) and apps.population.services.
reconcile_population() self-heals it on next run, resolving by name
(population_district_name, or dhis2_district_hint for the aggregate
rows) once Districts exist.
"""
from django.db import migrations

EXACT = 'exact'
AGGREGATE = 'aggregate'
UNMATCHED = 'unmatched'

# (population_district_name, dhis2_district_hint, match_type, notes)
MAPPING_ROWS = [
    ('Kailahun', '', EXACT, ''),
    ('Kenema', '', EXACT, ''),
    ('Kono', '', EXACT, ''),
    (
        'Bombali', '', EXACT,
        "DHIS2's boundary for this district likely predates the 2017 split that created Karene; "
        'this is an exact *name* match, boundary-exact is not guaranteed.',
    ),
    (
        'Falaba', '', UNMATCHED,
        'Split from Koinadugu in the 2017 administrative reorganisation; no DHIS2 org unit exists '
        'for it in this (pre-2017 boundary) DHIS2 instance. Excluded from DistrictPopulation and '
        'all ratio calculations; reported via PopulationDataQualityIssue instead.',
    ),
    (
        'Koinadugu', '', EXACT,
        "DHIS2's boundary for this district likely predates the 2017 split that created Falaba; "
        'this is an exact *name* match, boundary-exact is not guaranteed.',
    ),
    ('Tonkolili', '', EXACT, ''),
    ('Kambia', '', EXACT, ''),
    (
        'Karene', '', UNMATCHED,
        'Split from Bombali in the 2017 administrative reorganisation; no DHIS2 org unit exists '
        'for it in this (pre-2017 boundary) DHIS2 instance. Excluded from DistrictPopulation and '
        'all ratio calculations; reported via PopulationDataQualityIssue instead.',
    ),
    ('Port Loko', '', EXACT, ''),
    ('Bo', '', EXACT, ''),
    ('Bonthe', '', EXACT, ''),
    ('Moyamba', '', EXACT, ''),
    ('Pujehun', '', EXACT, ''),
    (
        'West Rural', 'Western Area', AGGREGATE,
        'Summed with West Urban into DHIS2\'s single "Western Area" org unit, which predates the '
        '2017 split of Western Area into Rural/Urban.',
    ),
    (
        'West Urban', 'Western Area', AGGREGATE,
        'Summed with West Rural into DHIS2\'s single "Western Area" org unit, which predates the '
        '2017 split of Western Area into Rural/Urban.',
    ),
]


def seed_mapping(apps, schema_editor):
    DistrictPopulationMapping = apps.get_model('population', 'DistrictPopulationMapping')
    District = apps.get_model('data_products', 'District')

    for population_name, dhis2_hint, match_type, notes in MAPPING_ROWS:
        dhis2_district = None
        if match_type != UNMATCHED:
            lookup_name = dhis2_hint or population_name
            dhis2_district = District.objects.filter(name=lookup_name).first()

        DistrictPopulationMapping.objects.get_or_create(
            population_district_name=population_name,
            defaults={
                'dhis2_district': dhis2_district,
                'dhis2_district_hint': dhis2_hint,
                'match_type': match_type,
                'notes': notes,
            },
        )


def noop_reverse(apps, schema_editor):
    # See apps/accounts/migrations/0001_seed_role_groups.py for the same
    # reasoning: not deleting on reverse, since a real reconciliation
    # may already depend on this mapping by the time anyone rolls it
    # back.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('population', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_mapping, noop_reverse),
    ]
