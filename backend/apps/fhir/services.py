"""FR6.3: real FHIR conformity validation and export orchestration.

validate_resource() is the actual conformity check the assessment
requires - it POSTs to a self-hosted HAPI FHIR R4 server's $validate
operation rather than trusting that hand-built dicts merely "look like"
FHIR. export_and_validate() is the only writer of FHIRValidationResult,
mirroring data_products.services' separation between pure building
(builders.py) and the orchestration/persistence layer.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class FHIRValidationError(Exception):
    """The validator itself was unreachable or returned something that
    isn't an OperationOutcome - distinct from a resource simply being
    invalid, which is a normal (non-exceptional) validate_resource result.
    """


def validate_resource(resource_type: str, resource_json: dict) -> dict:
    """POST one resource to {FHIR_VALIDATOR_URL}/{resource_type}/$validate.
    HAPI responds 200 with an OperationOutcome even when the resource is
    invalid - the outcome's issue severities are the actual verdict, not
    the HTTP status, so both cases are read the same way here.
    """
    url = f'{settings.FHIR_VALIDATOR_URL}/{resource_type}/$validate'
    try:
        response = requests.post(
            url,
            json=resource_json,
            headers={'Content-Type': 'application/fhir+json', 'Accept': 'application/fhir+json'},
            timeout=settings.FHIR_VALIDATOR_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise FHIRValidationError(f'Could not reach FHIR validator at {url}: {exc}') from exc

    try:
        outcome = response.json()
    except ValueError as exc:
        raise FHIRValidationError(
            f'FHIR validator returned a non-JSON response for {resource_type}: {response.text[:500]}'
        ) from exc

    if outcome.get('resourceType') != 'OperationOutcome':
        raise FHIRValidationError(
            f'Expected an OperationOutcome from the validator for {resource_type}, got: {outcome!r}'
        )

    issues = outcome.get('issue', [])
    is_valid = not any(issue.get('severity') in ('error', 'fatal') for issue in issues)
    if not is_valid:
        logger.warning('FHIR validation failed for %s: %r', resource_type, issues)
    return {'is_valid': is_valid, 'issues': issues}


def validate_bundle(bundle: dict) -> list[dict]:
    """Validates every individual resource inside the Bundle plus the
    Bundle itself (reference/structural consistency across entries).
    Returns one dict per resource, ready to persist as
    FHIRValidationResult rows.
    """
    results = []
    for entry in bundle['entry']:
        resource = entry['resource']
        outcome = validate_resource(resource['resourceType'], resource)
        results.append({
            'resource_type': resource['resourceType'],
            'resource_id': resource.get('id', ''),
            'fhir_json': resource,
            **outcome,
        })

    bundle_outcome = validate_resource('Bundle', bundle)
    results.append({
        'resource_type': 'Bundle',
        'resource_id': bundle.get('identifier', {}).get('value', ''),
        'fhir_json': bundle,
        **bundle_outcome,
    })
    return results


def export_and_validate(indicator) -> dict:
    """End to end for one Indicator: build the Bundle, validate every
    resource against the real FHIR server, and persist the results as
    conformity evidence.
    """
    from apps.fhir.builders import build_bundle
    from apps.fhir.models import FHIRValidationResult

    bundle = build_bundle(indicator)
    results = validate_bundle(bundle)

    saved = [
        FHIRValidationResult.objects.create(
            resource_type=result['resource_type'],
            resource_reference=f'{result["resource_type"]}/{result["resource_id"]} (indicator={indicator.name})',
            fhir_json=result['fhir_json'],
            is_valid=result['is_valid'],
            issues=result['issues'],
        )
        for result in results
    ]

    return {'bundle': bundle, 'results': saved}
