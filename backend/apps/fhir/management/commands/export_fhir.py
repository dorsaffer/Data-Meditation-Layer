import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit.context import audit_context
from apps.data_products.models import Indicator
from apps.fhir.services import FHIRValidationError, export_and_validate


class Command(BaseCommand):
    help = (
        'FR6.3: build FHIR R4 resources (Organization/Location/Measure/'
        'MeasureReport/Bundle/Provenance) for the given indicator(s) and '
        'validate every one against the self-hosted HAPI FHIR $validate '
        'operation. Writes each Bundle to fhir_exports/ and persists '
        'per-resource conformity evidence as FHIRValidationResult rows.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--indicator', nargs='+', default=None,
            help='DHIS2 data element UID(s) to export (default: all indicators with Observations)',
        )

    def handle(self, *args, **options):
        indicators = Indicator.objects.filter(observations__isnull=False).distinct()
        if options['indicator']:
            indicators = indicators.filter(dhis2_dx_uid__in=options['indicator'])

        if not indicators.exists():
            raise CommandError('No indicators with Observations found to export.')

        output_dir = settings.BASE_DIR / 'fhir_exports'
        output_dir.mkdir(exist_ok=True)

        total_valid = 0
        total_invalid = 0
        for indicator in indicators:
            self.stdout.write(f'Exporting "{indicator.name}" ({indicator.dhis2_dx_uid})...')
            try:
                with audit_context(actor='system:export_fhir'):
                    export = export_and_validate(indicator)
            except FHIRValidationError as exc:
                raise CommandError(str(exc))

            output_path = output_dir / f'{indicator.dhis2_dx_uid}_bundle.json'
            output_path.write_text(json.dumps(export['bundle'], indent=2))

            for result in export['results']:
                if result.is_valid:
                    total_valid += 1
                    self.stdout.write(self.style.SUCCESS(f'  OK    {result.resource_type} - valid'))
                else:
                    total_invalid += 1
                    self.stdout.write(self.style.ERROR(
                        f'  FAIL  {result.resource_type} - {len(result.issues)} issue(s): {result.issues}'
                    ))
            self.stdout.write(f'  Bundle written to {output_path}')

        summary_style = self.style.SUCCESS if total_invalid == 0 else self.style.ERROR
        self.stdout.write(summary_style(
            f'\nConformity summary: {total_valid} valid, {total_invalid} invalid (FHIR R4, '
            f'validated against {settings.FHIR_VALIDATOR_URL}).'
        ))
