"""Business logic for pulling DHIS2 data and persisting it. Keeps the
management command a thin CLI wrapper and client.py a pure DHIS2 API
concern with no Django model access.
"""
from __future__ import annotations

from apps.dhis2.client import DHIS2Client
from apps.dhis2.models import RawDHIS2Record


def fetch_and_store(dx: list[str], ou: str, pe: str) -> dict:
    """FR1.2/FR1.3/FR1.4: pull the given slice and store it unmodified,
    updating existing rows on their natural key instead of duplicating.
    """
    client = DHIS2Client()
    records = client.fetch_analytics(dx=dx, ou=ou, pe=pe)

    created = 0
    updated = 0
    for record in records:
        _obj, was_created = RawDHIS2Record.objects.update_or_create(
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
        if was_created:
            created += 1
        else:
            updated += 1

    return {'created': created, 'updated': updated, 'total': len(records)}
