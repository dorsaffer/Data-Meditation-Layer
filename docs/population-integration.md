# Population data integration (UHC district service coverage)

Enriches DHIS2 health-service data with district population so an analyst
can compute service activity as a share of population and identify
districts with relatively low reported activity — a Universal Health
Coverage (UHC) signal that DHIS2 service counts alone cannot provide.

## The population dataset

- **Source**: Statistics Sierra Leone (Stats SL), the national statistics
  office.
- **Dataset name**: 2021 Mid-Term Population and Housing Census (2021
  MTPHC) — Final Results by District.
- **Geographic coverage**: national, all 16 (post-2017) districts across 5
  regions.
- **Temporal coverage**: 2021 census reference year.
- **Refresh/update date**: final results released 2022-09-22; this is a
  point-in-time census, not a data feed — no further updates are expected
  until the next census.
- **Relevant fields used**: region, district, male, female, total, sex
  ratio. Only `total` (population) feeds the join; the rest is retained in
  `RawPopulationRecord` for traceability.
- **Converted to**: `backend/apps/population/data/population_by_district_2021.csv`
  (16 district-level rows; the source PDF's regional/national total rows
  are out of grain for a per-district join and are omitted — they're
  trivially re-derivable by summation if ever needed).

## Why this dataset

- Population provides a **denominator** for health-service activity: a
  raw count of visits means little without knowing how many people that
  district serves.
- It **enables comparison between districts with different population
  sizes** — a district with more reported visits isn't necessarily doing
  better if it also has a much larger population.
- It supports a **UHC analysis that cannot be derived from DHIS2 service
  activity alone**: UHC is fundamentally about population coverage, not
  service counts in isolation.

## Canonical models (apps/population)

Mirrors this codebase's existing raw-ingestion → canonical-transform split
(`apps.dhis2` → `apps.data_products`); here the "external system" is a
static CSV instead of an HTTP API:

- `RawPopulationRecord` — one unmodified row per CSV line (the
  traceability anchor, unique per district+reference year).
- `DistrictPopulationMapping` — the explicit, human-maintained geographic
  identifier mapping (see below). Editable via the Django admin.
- `DistrictPopulation` — canonical, reconciled population per
  `apps.data_products.District`, unique per district+reference year.
- `PopulationDataQualityIssue` — the data-quality report (see below).

`apps.population` imports only from `apps.data_products` (District,
Indicator, Observation) — never `apps.dhis2` or its client — so this
integration is independent of the DHIS2-specific acquisition layer.

## Geographic identifier reconciliation

The DHIS2 instance behind this app (`play.dhis2.org/dev`, a public demo)
uses Sierra Leone's **pre-2017** district boundaries (13 districts). The
2021 census uses **post-2017** boundaries (16 districts): Falaba was split
from Koinadugu, Karene was split from Bombali, and Western Area was split
into Western Area Rural / Western Area Urban. This mapping is deterministic,
reproducible, and maintained entirely in `DistrictPopulationMapping`
(seeded by `migrations/0002_seed_district_mapping.py`), not inferred by
name-matching logic at join time:

| Population district | → DHIS2 district | Match type | Note |
|---|---|---|---|
| Kailahun | Kailahun | exact | |
| Kenema | Kenema | exact | |
| Kono | Kono | exact | |
| Bombali | Bombali | exact | DHIS2 boundary likely predates the 2017 split that created Karene — name-exact, boundary-exact not guaranteed |
| Koinadugu | Koinadugu | exact | DHIS2 boundary likely predates the 2017 split that created Falaba — name-exact, boundary-exact not guaranteed |
| Tonkolili | Tonkolili | exact | |
| Kambia | Kambia | exact | |
| Port Loko | Port Loko | exact | |
| Bo | Bo | exact | |
| Bonthe | Bonthe | exact | |
| Moyamba | Moyamba | exact | |
| Pujehun | Pujehun | exact | |
| West Rural | Western Area | aggregate | summed with West Urban |
| West Urban | Western Area | aggregate | summed with West Rural |
| Falaba | *(none)* | unmatched | post-2017 split from Koinadugu, no DHIS2 counterpart |
| Karene | *(none)* | unmatched | post-2017 split from Bombali, no DHIS2 counterpart |

Unmatched rows are never silently dropped: they're excluded from
`DistrictPopulation` and from all ratio calculations, but recorded as
`PopulationDataQualityIssue` rows so they're visible in the data-quality
report.

## Data-quality report

`reconcile_population()` recomputes the full `PopulationDataQualityIssue`
set on every run (a live report of current state, not an accumulating
log). Each acceptance-criteria requirement maps to one issue type and one
tested code path (`apps/population/tests.py`):

| Issue type | Detected when |
|---|---|
| `missing_population` | A DHIS2 district has zero contributing population rows |
| `missing_dhis2_observation` | A district has a reconciled population but no DHIS2 observations at all |
| `unknown_district` | A population row's district has no mapping entry, or its mapping is documented `unmatched` |
| `duplicate_record` | A re-import reports a different total for a district+year than what's already stored (existing value is kept, not overwritten) |
| `conflicting_identifier` | A row's male + female ≠ its reported total |
| `out_of_period` | The population reference year falls outside the range of DHIS2 observation periods on file |
| `stale_data` | The population reference year is more than 3 years older than the most recent DHIS2 observation period |

Given this DB's real data (population reference year 2021; DHIS2 demo
periods run 2025–2026), both `out_of_period` and `stale_data` fire for
real, not just in a crafted test — a genuine, disclosed limitation of
combining a multi-year-old census with this demo instance's synthetic
recent periods.

## Derived metric: Service Activity Ratio

`compute_service_coverage(indicator_dx_uid, period, reference_year)`
(`GET /api/core/service-coverage/`):

```
Service Activity Ratio = Observation.value / DistrictPopulation.total_population
```

expressed as a percentage, per district. A district missing either side
is returned with `excluded: true` and a reason — never dropped or
defaulted to zero. Among districts with both sides resolved, the bottom
25% by ratio (at least 1) are flagged `potentially_underserved: true`.
This is a deterministic, dependency-free rule (sort + take the lowest
quartile), not a statistical model.

**This is a potential indicator, not a diagnosis.** Every response
includes a `caveat` field stating this explicitly — service-reporting
completeness, population estimate accuracy, and other contextual factors
can all affect the result. The frontend renders this caveat alongside the
data, not as fine print.

## Provenance

One `DataProduct` row, **"UHC District Service Coverage"** (created by
`manage.py create_uhc_coverage_product`), documents both sources via the
generic `DataProductSource` model (`apps.data_products` — reusable for any
future multi-source product, not population-specific):

- **Source 1**: Sierra Leone DHIS2 — aggregate service data; extraction
  date = the latest `RawDHIS2Record.fetched_at` on file.
- **Source 2**: Statistics Sierra Leone 2021 MTPHC — district population;
  reference period 2021.
- **Join**: `DataProduct.join_strategy` — the reconciliation described
  above.
- **Transformation**: `DataProduct.transformation_description` — the ratio
  formula above.

`DataProduct.indicator` is nullable specifically to support this product:
it's cross-indicator and cross-source by nature, unlike the
one-DataProduct-per-Indicator products `sync_data_product()` creates.

## Running it

```
cd backend
python manage.py migrate
python manage.py import_population          # reads the CSV, reconciles, reports issues
python manage.py create_uhc_coverage_product  # creates/updates the governance-catalog entry
python manage.py test apps.population apps.data_products
```

`import_population` is safe to re-run: raw records are upserted, and
`DistrictPopulation`/`PopulationDataQualityIssue` are recomputed from
scratch each time it reconciles.

## API access

`GET /api/core/district-population/`, `GET /api/core/population-data-quality-issues/`,
and `GET /api/core/service-coverage/` are gated to the `analyst` and
`auditor` roles (same as `Observations`/`FHIRValidationResult` — see
[docs/rbac.md](rbac.md)); `data_provider` and unauthenticated requests get
403/401 respectively. `DistrictPopulationMapping` is not exposed via API —
it's edited only through the Django admin, the same "governance judgement,
human-maintained" pattern as `DataProduct`'s own judgement fields.
