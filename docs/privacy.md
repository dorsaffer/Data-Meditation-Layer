# Privacy-preserving processing (FR6.7)

No real, identifiable patient data exists anywhere in this system — every record traces
back to the Sierra Leone DHIS2 **demo** instance (aggregate, district-level service
counts) or the 2021 census's published district population totals (see
[`population-integration.md`](population-integration.md)). There is no patient-level
resource anywhere in the canonical model or the FHIR export (`MeasureReport.type =
summary`, deliberately — see `apps/fhir/builders.py`'s module docstring).

That does **not** mean privacy risk is zero, and this system does not assume every DHIS2
field is automatically safe. Two real risks exist even in aggregate, district-level data:

1. **Free-text governance fields** (`DataProduct.purpose`, `.join_strategy`,
   `.transformation_description`, `DataProductSource.description`, `Indicator.
   description`) are typed by a human. Nothing stops a data steward from pasting a real
   name, phone number, or address into one of them.
2. **Small aggregate groups are themselves identifying.** "1 case of X in District Y" can
   re-identify a specific person even though no name or ID ever appears in the record — a
   classic small-cell disclosure risk, not a hypothetical one.

This document covers how those two risks are detected and controlled, and assesses the
prototype (not certifies it) against GDPR and HIPAA.

## Data classification taxonomy

`DataProduct.sensitivity_classification` (`apps/data_products/models.py`) implements the
spec's required 6-tier taxonomy, ordered least → most restrictive:

| Tier | Meaning | Example in this system |
|---|---|---|
| `public` | Safe for unrestricted release. | UHC District Service Coverage product (population ÷ service-activity ratio; explicitly reviewed and marked `public` by `create_uhc_coverage_product`). |
| `internal` | Fine for any authenticated, role-holding user; not for public release. | Default tier a data steward typically assigns to a clean, reviewed DHIS2 indicator product. |
| `sensitive` | Handle with care — narrower `permitted_audience`, not general "any role". | An indicator whose district-level pattern could reveal something about a specific facility or program the Ministry doesn't want broadly published. |
| `personal` | Contains or could plausibly re-derive information about an identifiable individual. | Not currently used by any product in this system — reserved for if patient- or facility-level data is ever added. |
| `potentially_identifying` | Not personal on its own, but combinable with other data to identify someone (a quasi-identifier). | A hypothetical future product with fine-grained geography + rare condition + narrow time window. |
| `prohibited` | Must never be published. **The model default** — see below. | Anything not yet reviewed by a human. |

**This is a governance judgement, never inferred from the data.** `sensitivity_
classification` is set once, by a human, through the Django admin, and every pipeline
function that touches a `DataProduct` (`sync_data_product`, `run_quality_checks`,
`apps.data_products.privacy`) explicitly never writes it — see the field's docstring in
`models.py`. The model default is `prohibited`, the most conservative tier: a brand-new,
unclassified `DataProduct` is blocked from publication the moment it's created, not after
someone forgets to classify it. `permitted_audience` (a list of role names) is the
same kind of human-only judgement call, for the same reason.

### Field/output classification (representative fields)

| Field / output | Classification | Why |
|---|---|---|
| `District.name`, `.dhis2_org_unit_uid` | Internal | Jurisdictional geography, not personal, but not meant for anonymous public release without review. |
| `Observation.value` | Internal → generalised at output | District×period aggregate count. Individually low-risk, but see small-cell control below — the *exact* value is never guaranteed safe at every possible granularity. |
| `DataProduct.purpose` / `.join_strategy` / `.transformation_description` | Internal, scanned | Free text — see PII free-text scan below. |
| `DataProduct.data_owner`, `.source` | Public | Organisational attribution, not personal data. |
| FHIR `MeasureReport` (exported bundle) | Inherits its `DataProduct`'s tier | `type=summary`, aggregate only, but still subject to the same small-cell generalisation as the API (`apps/fhir/builders.py::build_measure_report`). |
| `RawDHIS2Record.raw_payload` | Internal | Verbatim DHIS2 API response; not currently exposed through any read API to `analyst`/`auditor` at all — only `data_provider`/`auditor` can read raw records at all (see `docs/rbac.md`), and no endpoint surfaces `raw_payload` beyond that gate. |

## Identifier & quasi-identifier detection

Implemented in `apps/data_products/privacy.py`, run as part of `run_quality_checks()`
(`apps/data_products/quality.py`) — every time a data product's quality/privacy
assessment is (re)computed, both run together and feed the *same* publish decision.

**Direct identifiers** — `scan_text_for_identifiers()` regex-scans every free-text field
a human can type into (see the table above) for:

- email addresses
- phone numbers
- national-ID-shaped digit runs (9+ consecutive digits)
- street/plot addresses (`"12 Kroo Bay Road"`-shaped patterns)
- PII field-label leakage — literal labels like `Patient Name:`, `DOB:`, `MRN:`, `National
  ID Number:`, `Home Address:`, `Next of Kin:`

This is a **heuristic** control (method=`heuristic` in `QualityCheckResult`) — regexes
over natural language have both false positives and false negatives — but any match is
treated as a **blocker**, not a warning: publishing a real identifier is a categorically
worse outcome than an unnecessary manual review.

**Quasi-identifiers / small aggregate groups** — `_check_small_cell_disclosure_risk()`
flags any `Observation` whose value is below `SMALL_CELL_THRESHOLD` (5) as a disclosure
risk. This is a **heuristic warning**, not a blocker, precisely because the functional
control below already neutralises the risk before the value leaves the system — the check
exists so a human reviewing the assessment can *see* that small cells exist and why they
were generalised, not to gate on them a second time.

Every finding from both detectors is written as a `QualityCheckResult` row
(`check_code` prefixed `privacy_`) alongside FR6.6's data-quality checks, visible through
the same `DataProductViewSet` API, Django admin, and frontend Governance view already
built for FR6.6 (see [`data-quality.md`](data-quality.md)) — there is one assessment list,
not two.

## Functional privacy controls (implemented, not just described)

Three controls are actually enforced in code, not only documented:

### 1. Small-cell suppression (generalisation)

`apps.data_products.privacy.is_small_cell(value)` is the single predicate both output
paths call:

- `apps/data_products/serializers.py::ObservationSerializer` — `value` is a
  `SerializerMethodField`: a cell below the threshold is generalised to the threshold
  itself (never the true value, never null), and `is_suppressed: bool` tells the caller
  whether the number is exact or a generalised ceiling.
- `apps/fhir/builders.py::build_measure_report` — a disclosive count is emitted as a FHIR
  `Quantity` with `comparator: "<"` (e.g. `{"value": 5, "comparator": "<"}`) — the
  standard FHIR way to express "fewer than N" — so the true count never appears in an
  exported `MeasureReport` either.

This is real masking/generalisation of the value at every boundary where data leaves the
system (analytics API and FHIR export), not a display-only warning layered on top of the
real number.

### 2. PII free-text blocking

Any match from the direct-identifier scan is a `blocker`-severity `QualityCheckResult`.
`_apply_decision()` (`apps/data_products/quality.py`) already treats *any* blocker-severity
failure, regardless of which check produced it, as `blocked` — so a `DataProduct` with a
leaked email address in its `purpose` field cannot reach `publishable` until a steward
fixes the field and recomputes.

### 3. Sensitivity-tier publication gate (blocking above a risk threshold)

`_check_sensitivity_tier_gate()` blocks publication outright once
`sensitivity_classification` is `personal` or more restrictive
(`personal`/`potentially_identifying`/`prohibited`), *regardless of every other check*.
Combined with the `prohibited` default, this means: an unclassified `DataProduct` is
blocked from creation; a human must deliberately move it to `public`/`internal`/
`sensitive` (and separately complete FR6.6's `governance_reviewed` sign-off) before it can
ever be marked `publishable`.

### Hashing is not offered as anonymisation

No field in this system is hashed for privacy purposes, and this module does not offer
hashing as one of its controls. The spec is explicit that hashing alone must not be
described as anonymisation, and it would be a weak control here regardless — Sierra
Leone's district set has only 13–16 known values, so a hash of a district name is trivially
reversible by a lookup table.

## GDPR principles — assessment, not certification

| Principle | Assessment |
|---|---|
| Lawfulness, fairness, transparency | Not applicable in the legal sense — no real personal data is processed. This document itself is the transparency artefact for what the prototype *would* do with sensitive data. |
| Purpose limitation | `DataProduct.purpose` records why each product exists; nothing in the pipeline repurposes data silently. Not enforced technically (no purpose-based access control), only documented. |
| Data minimisation | Partially implemented: small-cell suppression is a minimisation control on output. Not implemented: no field-level minimisation on ingestion — `RawDHIS2Record.raw_payload` retains the full DHIS2 response verbatim for traceability, which is a trade-off (see Provenance) the codebase makes deliberately, not an oversight. |
| Accuracy | Covered by FR6.6's quality checks (impossible values, outliers, stale data), not by this module. |
| Storage limitation | **Not implemented.** No retention policy, no automated deletion/archival of `RawDHIS2Record` or `Observation` rows. This is a real gap, not a design choice. |
| Integrity & confidentiality | Partially implemented: RBAC gates read access (`docs/rbac.md`), the FR6.7 controls above gate what a permitted reader sees. Not implemented: encryption at rest, TLS termination/config (out of scope for local docker-compose), secrets management beyond `.env` (see `docs/threat-model.md` if produced separately). |
| Accountability | Partially implemented: every `QualityCheckResult` and the human `governance_reviewed`/`sensitivity_classification` decisions are visible and attributable through the admin. **Not implemented: no audit log of *who* viewed or changed what and when** — see Known risks below; this is FR6.8 scope, not yet built. |

## HIPAA — recognised safeguards, assessed honestly

This is a Sierra Leone DHIS2 system, not a US covered entity — HIPAA does not legally
apply. It's used here only as a recognised safeguards checklist, per the brief.

| Safeguard category | Assessment |
|---|---|
| Administrative (access management, workforce training, sanctions) | Partially implemented: role-based access control exists and is enforced server-side (`docs/rbac.md`). Not implemented: no training/sanctions process (out of scope for a prototype), no formal risk-assessment cadence beyond this document. |
| Physical (facility access, workstation/device security) | **Out of scope.** This runs in local docker-compose / whatever host it's deployed to; no physical-security controls exist or are claimed. |
| Technical (access control, audit controls, integrity, transmission security) | Partially implemented: access control (RBAC) and the FR6.7 controls above (integrity of what's disclosed). **Not implemented: audit controls** (no log of access events — FR6.8), **not implemented: transmission security** (no TLS is configured between the compose services; would be required before any real deployment). |

No claim of HIPAA or GDPR certification/compliance is made anywhere in this codebase or
its documentation. This table exists to state plainly what's implemented, what's a real
gap, and what production would additionally require.

## Known risks / not yet implemented

- **No audit log.** FR6.8 (RBAC + `AuditEvent`/`Provenance` audit trail) has not been
  built yet — there is currently no record of *who* read or exported a `DataProduct`'s
  data, only of the governance decisions made about it.
- **`permitted_audience` is not cross-checked against the requesting user's roles.** It's
  stored governance metadata (a list of role-name strings) but no view currently filters
  results by it — RBAC today is coarse (a role sees all rows of an endpoint it's allowed
  to call, or none). Tightening this to per-product audience enforcement is a real gap.
- **The PII free-text scan is regex-based and English-oriented.** It will miss identifiers
  in formats it wasn't written for (e.g. non-Western name/address conventions, ID formats
  outside the patterns above) and can false-positive on legitimate text. It is a net rather
  than a guarantee.
- **No storage-limitation/retention policy** for `RawDHIS2Record` or `Observation` (GDPR
  gap above).
- **No encryption at rest or in transit** between the docker-compose services.

## What would be required before production deployment

1. Build FR6.8's audit log (`AuditEvent`) so every read/export of a non-`public` product
   is attributable and reviewable — this is the single largest gap relative to a real
   production posture.
2. Enforce `permitted_audience` at the query layer, not just store it.
3. TLS between every service, and a real secrets manager instead of `.env`.
4. A retention/deletion policy for raw and canonical records, with automated enforcement.
5. Extend the PII scanner (or replace it with a maintained NER-based tool) once real,
   non-demo source data with a realistic risk of embedded identifiers is in scope.
6. A second reviewer (not the implementer) sign-off step on `sensitivity_classification`
   changes, since it's currently a single-admin judgement call with no four-eyes check.

## Running the tests that prove this

```
cd backend
python manage.py test apps.data_products apps.fhir
```

`apps/data_products/tests.py`: `ScanTextForIdentifiersTests`, `IsSmallCellTests`,
`RunPrivacyChecksTests` (sensitivity-tier blocking, PII-in-free-text blocking, small-cell
warning-not-blocker, the `prohibited` fail-closed default), `ObservationSerializerSuppressionTests`
(the small-cell value is actually generalised in the API response, not just flagged).
`apps/fhir/tests.py`: `test_build_measure_report_suppresses_small_cell_value` and
`test_build_measure_report_does_not_suppress_value_at_threshold` (the same control at the
FHIR export boundary).
