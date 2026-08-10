from django.core.management.base import BaseCommand, CommandError

from apps.core.models import RawDHIS2Record
from apps.core.services.dhis2_client import DHIS2Client, DHIS2ClientError


class Command(BaseCommand):
    help = (
        'FR1.2/FR1.3/FR1.4: pull DHIS2 analytics data for the given data '
        'elements/org unit/period and store it unmodified. Re-running '
        'updates existing rows instead of duplicating them.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dx', nargs='+', default=['fbfJHSPpUQD'],
            help='Data element/indicator UID(s) (default: ANC 1st visit)',
        )
        parser.add_argument('--ou', default='LEVEL-2', help='Org unit level or UID (default: LEVEL-2, districts)')
        parser.add_argument('--pe', default='LAST_12_MONTHS', help='Period (default: LAST_12_MONTHS)')

    def handle(self, *args, **options):
        client = DHIS2Client()
        try:
            records = client.fetch_analytics(dx=options['dx'], ou=options['ou'], pe=options['pe'])
        except DHIS2ClientError as exc:
            raise CommandError(str(exc))

        created_count = 0
        updated_count = 0
        for record in records:
            _obj, created = RawDHIS2Record.objects.update_or_create(
                dx_uid=record['dx_uid'],
                org_unit_uid=record['org_unit_uid'],
                period=record['period'],
                defaults={
                    'dx_name': record['dx_name'],
                    'org_unit_name': record['org_unit_name'],
                    'value': record['value'],
                    'raw_payload': record['raw_payload'],
                    'source_url': record['source_url'],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created_count}, Updated: {updated_count}, Total rows: {len(records)}'
        ))
