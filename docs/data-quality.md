# Data quality assessment & publication decision (FR6.6)

Before any `DataProduct` is treated as available to analytical users, this system runs a
visible data-quality assessment and resolves it into one of four states:

| `quality_status`             | Meaning                                                                 |
|-------------------------------|--------------------------------------------------------------------------|
| `unscreened`                 | No assessment has run yet.                                              |
| `publishable`                | Every check passed.                                                     |
| `publishable_with_warnings`  | No blocking or human-approval failures, but at least one warning-level check failed. |
| `blocked`                    | At least one blocker-severity check failed, or governance review is still pending. |

The assessment result — every individual check, not just the rolled-up decision — is
stored (`QualityCheckResult`, one row per check per product) and surfaced through the
existing `DataProductViewSet` API (`quality_checks` on each product), the Django admin,
and the frontend (Analytics → Data quality & conformity, each product's detail page, and
Governance).

## Where the logic lives

`backend/apps/data_products/quality.py`, `run_quality_checks(product)`. It is the only
writer of `QualityCheckResult` and of `DataProduct.quality_status` — the same
single-owner-function convention already used by
`apps.data_products.services.sync_data_product` for the other pipeline-derived fields.

It is **idempotent**: every call deletes and recomputes the product's check set from
current state (the same pattern already used by
`apps.population.services.reconcile_population` for `PopulationDataQualityIssue`). It
runs automatically at the end of the two pipeline management commands
(`transform_to_canonical`, `create_uhc_coverage_product`), and can be re-triggered
on demand for one or more products via the "Recompute FR6.6 data-quality assessment"
action in the Django admin's Data Product list — the mechanism a data steward uses to
see a decision update immediately after toggling governance review.

## The checks

Every check is tagged with a `method`, so a human reading a "passed" knows how much to
trust it without re-checking it themselves:

- **`deterministic`** — a hard fact: a regex match, a count, a database constraint. No
  judgement call, no false positives.
- **`heuristic`** — a statistical judgement call (e.g. an outlier threshold) that can
  have false positives or false negatives. Flags something for review; it is not proof
  of a data error.
- **`human_required`** — never evaluated by code at all. Reads a decision a person
  already made and fails closed until they make it.

| Check                              | Category (spec)               | Method          | Severity | What it checks |
|-------------------------------------|--------------------------------|-----------------|----------|-----------------|
| Completeness                        | Completeness                   | Deterministic   | Blocker (zero data) / Warning (partial) | Observed vs. expected district×period rows for the indicator. |
| Duplicate records                   | Duplicate records               | Deterministic   | Info (always passes) | Documents that `unique_observation_indicator_district_period` and `unique_dhis2_record_dx_ou_period` make a duplicate row structurally impossible — not re-derived. |
| Valid period format                 | Invalid dates                  | Deterministic   | Blocker  | Every period matches DHIS2's `YYYY`/`YYYYMM` shape. |
| Valid identifier format             | Invalid codes                  | Deterministic   | Blocker  | Every `dx_uid`/`org_unit_uid` matches the DHIS2 UID pattern. |
| Impossible values                   | Impossible values               | Deterministic   | Blocker  | No negative observation values. |
| Suspicious values (outliers)        | Suspicious values                | **Heuristic**   | Warning  | Per-period z-score outliers (`\|z\| > 3`) across districts; skipped (not "passed") when fewer than 3 comparable districts exist. |
| Geographic identifier consistency   | Inconsistent geographic IDs    | Deterministic   | Blocker  | No two districts referenced by the product share a name with a different DHIS2 org-unit UID. |
| Stale data                          | Stale data                      | Deterministic (policy threshold) | Warning | `refresh_date` age vs. a 180-day threshold. The threshold itself is a policy choice, documented here; the comparison against it is a hard fact. |
| Governance review                   | *(publication gate, not a spec category — added because a publish decision needs one)* | **Human-required** | Blocker | Reads `DataProduct.governance_reviewed`. A data steward must review `sensitivity_classification`/`permitted_audience` and check this box in the admin — the assessment cannot pass this on its own, by design. |

### The one multi-source product (UHC District Service Coverage)

`DataProduct.indicator` is nullable specifically for this one cross-source,
cross-indicator product (see its model docstring). It has no `Observation` set of its
own to check directly — `apps.population.services.reconcile_population()` already
computes its quality signal as `PopulationDataQualityIssue` rows. Rather than
re-deriving the same logic a second time, `run_quality_checks` rolls those issue counts
up into the same `QualityCheckResult` shape (completeness ← missing
population/observation issues, duplicate records ← duplicate-record issues, impossible
values ← conflicting male+female/total issues, geographic identifier consistency ←
unknown-district issues, stale data ← stale/out-of-period issues), plus the same
governance-review gate. All of these are `deterministic` — `reconcile_population`
performs no statistical inference.

## The decision rule

Given a product's freshly computed `QualityCheckResult` set:

1. If any `human_required` check failed, **or** any `blocker`-severity check failed →
   `blocked`.
2. Else if any check failed (necessarily `warning`/`info` severity at this point) →
   `publishable_with_warnings`.
3. Else → `publishable`.
4. If no checks exist yet (never run) → `unscreened`.

In practice this means: **a data product can never reach `publishable` until a human has
explicitly reviewed it**, regardless of how clean the automated checks are — the
governance-review gate is a hard blocker, not a warning.
