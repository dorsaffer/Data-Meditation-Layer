"""privacy-preserving processing.

This module is the counterpart to apps.data_products.quality for
privacy rather than data quality, but deliberately writes into the same
QualityCheckResult table and feeds the same run_quality_checks()/
_apply_decision() publish gate — a DataProduct that leaks an identifier
or sits at a high sensitivity tier must be just as blocked from
"publishable" as one that fails a completeness check, and this codebase
already has exactly one decision rule for that ("any blocker anywhere
blocks publish"). Building a second, parallel decision table here would
just be a second place for that rule to drift out of sync. Each check
this module writes uses a check_code prefixed `privacy_` so it stays
visibly distinguishable from FR6.6's checks in the same list.

Three controls, matching the spec's three asks:

1. sensitivity_tier_gate — reads (never writes) DataProduct.
   sensitivity_classification and blocks publication outright once it's
   PERSONAL or more restrictive. This is the "blocking of a dataset when
   a risk threshold is exceeded" control. Deterministic: it's a lookup
   against a fixed tier ordering, not a judgement call.

2. pii_free_text_scan — every free-text field a human can type into
   (DataProduct.purpose/join_strategy/transformation_description,
   DataProductSource.name/description, Indicator.description) is
   regex-scanned for direct identifiers: email addresses, phone
   numbers, national-ID-shaped digit runs, street/plot addresses, and
   PII field-label leakage ("patient name:", "DOB", "MRN", ...). This
   is heuristic, not deterministic - free text is exactly where a
   well-intentioned data steward can accidentally paste something they
   shouldn't have, and regexes over natural language always have false
   positives/negatives - but any match is treated as a blocker rather
   than a warning, because the cost of silently publishing a real
   identifier is categorically worse than the cost of a false-positive
   review.

3. small_cell_disclosure_risk — flags Observations whose value is below
   SMALL_CELL_THRESHOLD as a quasi-identifier risk (a district/period
   cell that small can itself re-identify someone, e.g. "1 case of X in
   District Y"). This is the *detection* half; is_small_cell() below is
   the actual *functional control* - it's called from
   apps.data_products.serializers and apps.fhir.builders to generalise
   the true value to "< threshold" everywhere the value would otherwise
   leave the system, not just to flag it here. Kept as a warning, not a
   blocker: a handful of small cells in an otherwise clean product
   shouldn't block the whole product the way a leaked identifier does,
   precisely because the suppression control already neutralises the
   risk at the output boundary.

Hashing is deliberately not offered as an option anywhere in this
module: the spec is explicit that hashing alone must not be described
as anonymisation (it's reversible with a small input space, e.g. a
lookup table of the ~13 Sierra Leone district names), and nothing in
this codebase's data is currently hashed for privacy purposes.
"""
from __future__ import annotations

import re
from typing import Iterable

from apps.data_products.models import DataProduct, Observation, QualityCheckResult

SMALL_CELL_THRESHOLD = 5

Method = QualityCheckResult.Method
Severity = QualityCheckResult.Severity

# Tiers below PERSONAL may be published (subject to every other FR6.6/
# FR6.7 check still passing); PERSONAL and above always block, because
# no automated check here can substitute for the human judgement that
# assigned that tier in the first place.
PUBLISHABLE_TIERS = {
    DataProduct.SensitivityClassification.PUBLIC,
    DataProduct.SensitivityClassification.INTERNAL,
    DataProduct.SensitivityClassification.SENSITIVE,
}

# Deliberately conservative and DHIS2/Sierra-Leone-context-agnostic:
# these patterns exist to catch a human typing real contact/identity
# details into a free-text governance field, not to be a general-purpose
# PII scrubber. False positives (e.g. a UN office phone number quoted in
# a data_owner description) are an acceptable cost given a match blocks
# publication and is always human-reviewable in the admin.
_PII_PATTERNS: dict[str, re.Pattern] = {
    'email address': re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    'phone number': re.compile(r'(\+?\d[\d\-\s]{7,}\d)'),
    'national ID-shaped number': re.compile(r'\b\d{9,}\b'),
    'street/plot address': re.compile(
        r'\b\d+\s+[A-Za-z]+\s+(Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Close|Drive|Plot)\b', re.IGNORECASE
    ),
    'PII field-label leakage': re.compile(
        r'\b(patient\s*name|full\s*name|date\s*of\s*birth|\bDOB\b|\bMRN\b|national\s*ID\s*number|'
        r'\bNIN\b|\bSSN\b|home\s*address|next\s*of\s*kin)\s*[:=]', re.IGNORECASE
    ),
}


def scan_text_for_identifiers(text: str) -> list[str]:
    """Return the names of every _PII_PATTERNS category matched in `text`."""
    if not text:
        return []
    return [label for label, pattern in _PII_PATTERNS.items() if pattern.search(text)]


def _free_text_fields(product: DataProduct) -> Iterable[tuple[str, str]]:
    yield 'purpose', product.purpose
    yield 'join_strategy', product.join_strategy
    yield 'transformation_description', product.transformation_description
    for source in product.sources.all():
        yield f'source "{source.name}" name', source.name
        yield f'source "{source.name}" description', source.description
    if product.indicator_id is not None:
        yield 'indicator description', product.indicator.description


def is_small_cell(value: float, threshold: int = SMALL_CELL_THRESHOLD) -> bool:
    """The one predicate both the API serializer and the FHIR builder
    call to decide whether a value must be generalised before it leaves
    the system. Kept here, not duplicated, so the threshold has exactly
    one definition.
    """
    return value < threshold


def _record(product: DataProduct, *, code: str, name: str, method: str, severity: str, passed: bool, detail: str):
    return QualityCheckResult.objects.create(
        data_product=product, check_code=code, check_name=name,
        method=method, severity=severity, passed=passed, detail=detail,
    )


def _truncate(items: Iterable[str], limit: int = 5) -> str:
    items = list(items)
    shown = ', '.join(items[:limit])
    if len(items) > limit:
        shown += f', … ({len(items) - limit} more)'
    return shown


def run_privacy_checks(product: DataProduct) -> None:
    """Called from apps.data_products.quality.run_quality_checks(), after
    that function's own FR6.6 checks and before _apply_decision(), so a
    privacy blocker and a quality blocker are indistinguishable to the
    publish decision - both simply block. Writes no field on `product`
    itself other than through the QualityCheckResult rows it creates;
    like every other check in this codebase it never touches
    sensitivity_classification.
    """
    _check_sensitivity_tier_gate(product)
    _check_pii_free_text_scan(product)
    if product.indicator_id is not None:
        _check_small_cell_disclosure_risk(product)


def _check_sensitivity_tier_gate(product: DataProduct) -> None:
    passed = product.sensitivity_classification in PUBLISHABLE_TIERS
    _record(
        product, code='privacy_sensitivity_tier_gate', name='Sensitivity tier gate',
        method=Method.DETERMINISTIC, severity=Severity.BLOCKER, passed=passed,
        detail=(
            f'sensitivity_classification={product.sensitivity_classification!r} is at or below the '
            f'publishable tier.' if passed else
            f'sensitivity_classification={product.sensitivity_classification!r} is PERSONAL or more '
            f'restrictive - blocked from publication regardless of every other check until a data '
            f'steward reclassifies it.'
        ),
    )


def _check_pii_free_text_scan(product: DataProduct) -> None:
    findings = []
    for field_label, text in _free_text_fields(product):
        for category in scan_text_for_identifiers(text):
            findings.append(f'{field_label}: possible {category}')

    passed = not findings
    _record(
        product, code='privacy_pii_free_text_scan', name='PII free-text scan',
        method=Method.HEURISTIC, severity=Severity.BLOCKER, passed=passed,
        detail=(
            'No direct-identifier patterns found in free-text governance fields.' if passed else
            f'Possible identifier(s) found in free text: {_truncate(findings)}. Heuristic - review and '
            f'correct the field(s), then recompute.'
        ),
    )


def _check_small_cell_disclosure_risk(product: DataProduct) -> None:
    small_cells = list(
        Observation.objects
        .filter(indicator=product.indicator, value__lt=SMALL_CELL_THRESHOLD)
        .select_related('district')
        .values_list('district__name', 'period', 'value')
    )
    passed = not small_cells
    _record(
        product, code='privacy_small_cell_disclosure_risk', name='Small-cell disclosure risk',
        method=Method.HEURISTIC, severity=Severity.WARNING, passed=passed,
        detail=(
            f'No district×period cell below {SMALL_CELL_THRESHOLD}.' if passed else
            f'{len(small_cells)} cell(s) below {SMALL_CELL_THRESHOLD} — a small aggregate group can '
            f'itself be identifying: {_truncate(f"{d}/{p}={v}" for d, p, v in small_cells)}. Generalised '
            f'to "< {SMALL_CELL_THRESHOLD}" in every API/FHIR output by apps.data_products.privacy.'
            f'is_small_cell() - not a data error, no action required.'
        ),
    )
