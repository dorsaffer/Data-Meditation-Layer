"""Business logic for pulling DHIS2 data and persisting it. Keeps the
management command a thin CLI wrapper and client.py a pure DHIS2 API
concern with no Django model access.
"""
from __future__ import annotations

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.dhis2.client import DHIS2Client, DHIS2ClientError
from apps.dhis2.models import RawDHIS2Record


def fetch_and_store(dx: list[str], ou: str, pe: str) -> dict:
    """pull the given slice and store it unmodified,
    updating existing rows on their natural key instead of duplicating.

    FR6.8: audited as a DATA_ACQUISITION event either way - a failed pull
    from the source system is exactly the kind of thing an auditor needs
    to see, not just an operator watching stdout.
    """
    client = DHIS2Client()
    try:
        records = client.fetch_analytics(dx=dx, ou=ou, pe=pe)
    except DHIS2ClientError as exc:
        record_event(
            AuditEvent.Action.DATA_ACQUISITION, AuditEvent.Outcome.FAILURE,
            resource_type='RawDHIS2Record',
            detail={'dx': dx, 'ou': ou, 'pe': pe, 'error': str(exc)},
        )
        raise

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

    record_event(
        AuditEvent.Action.DATA_ACQUISITION, AuditEvent.Outcome.SUCCESS,
        resource_type='RawDHIS2Record',
        detail={'dx': dx, 'ou': ou, 'pe': pe, 'created': created, 'updated': updated, 'total': len(records)},
    )
    return {'created': created, 'updated': updated, 'total': len(records)}
