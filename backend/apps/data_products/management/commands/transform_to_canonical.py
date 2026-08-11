from django.core.management.base import BaseCommand

from apps.audit.context import audit_context
from apps.data_products.models import Indicator
from apps.data_products.quality import run_quality_checks
from apps.data_products.services import sync_data_product, transform_raw_records


class Command(BaseCommand):
    help = (
        'FR2: transform RawDHIS2Record rows into the canonical model '
        '(District/Indicator/Observation), sync DataProduct governance metadata, and run '
        'the FR6.6 data-quality assessment.'
    )

    def handle(self, *args, **options):
        with audit_context(actor='system:transform_to_canonical'):
            result = transform_raw_records()
            self.stdout.write(self.style.SUCCESS(
                f"Observations created: {result['created']}, updated: {result['updated']}, "
                f"skipped (non-numeric): {result['skipped']}"
            ))

            indicators = Indicator.objects.filter(id__in=result['indicator_ids'])
            for indicator in indicators:
                product = sync_data_product(indicator)
                product = run_quality_checks(product)
                self.stdout.write(
                    f'  DataProduct synced: "{product.title}" '
                    f'(transformation_status={product.transformation_status}, '
                    f'quality_status={product.quality_status}, '
                    f'coverage={product.temporal_coverage_start}..{product.temporal_coverage_end})'
                )
