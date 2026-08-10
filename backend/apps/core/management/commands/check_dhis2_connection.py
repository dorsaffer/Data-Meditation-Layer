from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.services.dhis2_client import DHIS2Client, DHIS2ClientError


class Command(BaseCommand):
    help = 'FR1.1: verify the configured DHIS2 instance is reachable and credentials are valid.'

    def handle(self, *args, **options):
        self.stdout.write(f'Connecting to {settings.DHIS2_BASE_URL} ...')
        try:
            info = DHIS2Client().check_connection()
        except DHIS2ClientError as exc:
            self.stderr.write(self.style.ERROR(f'Connection failed: {exc}'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS('Connected.'))
        for key, value in info.items():
            self.stdout.write(f'  {key}: {value}')
