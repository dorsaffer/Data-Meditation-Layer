from django.core.management.base import BaseCommand

from apps.data_products.models import DataProduct, DataProductSource, Observation
from apps.dhis2.models import RawDHIS2Record
from apps.population.models import DistrictPopulationMapping
from apps.population.services import SERVICE_COVERAGE_CAVEAT

PRODUCT_TITLE = 'UHC District Service Coverage'

PURPOSE = (
    'Reported DHIS2 service activity read alone has no denominator: 20,000 visits means something '
    'different in a district of 300,000 people than in one of 800,000. Joining district population '
    '(a) provides that denominator, (b) enables comparison between districts with different '
    'population sizes on equal footing, and (c) supports Universal Health Coverage analysis that '
    'cannot be derived from DHIS2 service activity alone - population coverage, not just service '
    'counts, is the UHC question. ' + SERVICE_COVERAGE_CAVEAT
)

JOIN_STRATEGY = (
    'District identifier mapping (apps.population.DistrictPopulationMapping), reconciling the 2021 '
    'census\'s 16 post-2017 districts against this DHIS2 instance\'s 13 pre-2017 districts: 12 exact '
    'name matches; West Rural + West Urban summed into DHIS2\'s single "Western Area" district '
    '(aggregate match); Falaba and Karene (both post-2017 splits) have no DHIS2 counterpart and are '
    'excluded from DistrictPopulation and all ratio calculations, but are recorded as '
    'PopulationDataQualityIssue rows rather than silently dropped. Deterministic and reproducible: '
    'the mapping table, not name-matching logic, drives every run of reconcile_population().'
)

TRANSFORMATION_DESCRIPTION = (
    'Service Activity Ratio = Observation.value (reported service activity, per indicator/district/'
    'period) / DistrictPopulation.total_population (per district/reference year), expressed as a '
    'percentage. Districts missing either side are excluded from the ratio and reported as such, '
    'never defaulted to zero. See apps.population.services.compute_service_coverage.'
)


class Command(BaseCommand):
    help = (
        'Create/update the single governance-catalog DataProduct documenting the population + '
        'DHIS2 integration, with retained provenance for both sources. Run after import_population.'
    )

    def handle(self, *args, **options):
        mapping_qs = DistrictPopulationMapping.objects.all()
        exact = mapping_qs.filter(match_type=DistrictPopulationMapping.MatchType.EXACT).count()
        # Aggregate is counted by distinct target DHIS2 district, not by mapping row: two
        # population rows (West Rural + West Urban) collapse into one DHIS2 district (Western Area).
        aggregate = (
            mapping_qs.filter(match_type=DistrictPopulationMapping.MatchType.AGGREGATE)
            .values('dhis2_district').distinct().count()
        )
        unmatched = mapping_qs.filter(match_type=DistrictPopulationMapping.MatchType.UNMATCHED).count()
        reconciled_districts = exact + aggregate

        periods = list(Observation.objects.values_list('period', flat=True))
        latest_raw = RawDHIS2Record.objects.order_by('-fetched_at').first()

        product, _created = DataProduct.objects.update_or_create(
            title=PRODUCT_TITLE,
            indicator=None,
            defaults={
                'purpose': PURPOSE,
                'data_owner': 'Ministry of Health — HMIS Unit',
                'source': (
                    'Sierra Leone DHIS2 (aggregate service data) + Statistics Sierra Leone 2021 MTPHC '
                    '(district population, Final Results by District, released 2022-09-22)'
                ),
                'geographic_coverage': (
                    f'Sierra Leone — {reconciled_districts} of 13 DHIS2 districts reconciled with '
                    f'population data ({exact} exact matches, {aggregate} district(s) reached via an '
                    f'aggregate match); {unmatched} census districts (Falaba, Karene) have no DHIS2 '
                    f'counterpart and are excluded.'
                ),
                'temporal_coverage_start': min(periods) if periods else '',
                'temporal_coverage_end': max(periods) if periods else '',
                'schema_version': '1.0',
                'sensitivity_classification': DataProduct.SensitivityClassification.PUBLIC,
                'transformation_status': DataProduct.TransformationStatus.CANONICAL,
                'permitted_audience': ['analyst', 'auditor'],
                'join_strategy': JOIN_STRATEGY,
                'transformation_description': TRANSFORMATION_DESCRIPTION,
            },
        )

        DataProductSource.objects.update_or_create(
            data_product=product, name='Sierra Leone DHIS2',
            defaults={
                'description': 'Aggregate health-service indicator data (reported service activity).',
                'extraction_date': latest_raw.fetched_at.date() if latest_raw else None,
            },
        )
        DataProductSource.objects.update_or_create(
            data_product=product, name='Statistics Sierra Leone — 2021 Mid-Term Population and Housing Census',
            defaults={
                'description': 'District-level population (Final Results by District, released 2022-09-22).',
                'reference_period': '2021',
            },
        )

        self.stdout.write(self.style.SUCCESS(f'DataProduct "{PRODUCT_TITLE}" ready with 2 sources.'))
