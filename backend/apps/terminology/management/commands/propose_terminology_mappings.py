from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.data_products.models import Indicator
from apps.terminology.services import review_mapping, suggest_mappings_for_indicator


class Command(BaseCommand):
    help = (
        'FR6.4: run the semantic-search heuristic against every Indicator and '
        'create PROPOSED terminology mappings for whatever it matches. Never '
        'creates an ACCEPTED mapping - pass --accept-as <username> to also have '
        'a named, real user review and accept the proposals in the same run '
        '(useful for demoing the end-to-end flow), otherwise every proposal is '
        'left for a data steward to review in the Django admin.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--accept-as', default=None,
            help='Username of an existing user to immediately review+accept the new proposals as.',
        )

    def handle(self, *args, **options):
        proposed = []
        for indicator in Indicator.objects.all():
            proposed += suggest_mappings_for_indicator(indicator)

        if not proposed:
            self.stdout.write('No new candidate mappings found.')
            return

        for mapping in proposed:
            self.stdout.write(
                f'  PROPOSED: {mapping.source_code} ({mapping.source_display}) -> '
                f'{mapping.target_terminology}:{mapping.target_code} (confidence={mapping.confidence})'
            )

        username = options['accept_as']
        if not username:
            self.stdout.write(self.style.SUCCESS(
                f'{len(proposed)} mapping(s) proposed. Review them in the Django admin '
                '(Terminology mappings) before they can be used by the FHIR pipeline.'
            ))
            return

        try:
            reviewer = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No such user {username!r} - proposals left as PROPOSED.'))
            return

        for mapping in proposed:
            review_mapping(mapping, reviewer=reviewer, approve=True, rationale=mapping.rationale)
        self.stdout.write(self.style.SUCCESS(
            f'{len(proposed)} mapping(s) proposed and accepted as {username!r}.'
        ))
