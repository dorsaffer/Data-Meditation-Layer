from django.core.management.base import BaseCommand, CommandError

from apps.dhis2.client import DHIS2ClientError
from apps.dhis2.services import fetch_and_store


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
        try:
            result = fetch_and_store(dx=options['dx'], ou=options['ou'], pe=options['pe'])
        except DHIS2ClientError as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {result['created']}, Updated: {result['updated']}, Total rows: {result['total']}"
        ))
