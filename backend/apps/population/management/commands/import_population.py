from pathlib import Path

from django.core.management.base import BaseCommand

from apps.population.services import import_population_csv, reconcile_population

DEFAULT_CSV_PATH = Path(__file__).resolve().parents[2] / 'data' / 'population_by_district_2021.csv'


class Command(BaseCommand):
    help = (
        'Import the district population CSV and reconcile it against DHIS2 districts. '
        'Re-running is safe: raw records are upserted, and DistrictPopulation/'
        'PopulationDataQualityIssue are recomputed from scratch each time.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--path', default=str(DEFAULT_CSV_PATH), help='Path to the population CSV.')
        parser.add_argument('--reference-year', type=int, default=2021)

    def handle(self, *args, **options):
        import_result = import_population_csv(options['path'], reference_year=options['reference_year'])
        self.stdout.write(self.style.SUCCESS(
            f"Imported. Created: {import_result['created']}, Updated: {import_result['updated']}, "
            f"Conflicts flagged: {import_result['conflicts']}"
        ))

        reconcile_result = reconcile_population(reference_year=options['reference_year'])
        self.stdout.write(self.style.SUCCESS(
            f"Reconciled. Districts with population: {reconcile_result['districts_reconciled']}, "
            f"Data-quality issues: {reconcile_result['issues']}"
        ))
