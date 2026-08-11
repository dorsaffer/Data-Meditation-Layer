# Terminology mapping (FR6.4)

Maps a DHIS2 data element (or a local concept with no DHIS2 origin) to a
recognised terminology / controlled code system, as an explicit,
human-reviewed record — independent of both the DHIS2 acquisition
connector (`apps.dhis2`) and the canonical model (`apps.data_products`).

## Where it lives

`apps/terminology/` — a standalone Django app.

- `models.py` — `TerminologyMapping`: one row per proposed/accepted/rejected/
  unmapped source→target pairing. Fields: `source_system`, `source_code`,
  `source_display`, `target_terminology` (ICD-10 / ICD-11 / LOINC / SNOMED CT
  / Other), `target_code`, `target_display`, `terminology_version`, `status`,
  `mapping_method`, `confidence`, `rationale`, `reviewer`, `reviewed_at`.
- `services.py` — the only place mapping status is allowed to change:
  - `propose_mapping()` / `suggest_mappings_for_indicator()` — create
    `PROPOSED` rows only. This is the entry point for manual proposals *and*
    for the heuristic "semantic search" matcher — neither path can reach
    `ACCEPTED`.
  - `review_mapping()` — the *only* function that can set `ACCEPTED` or
    `REJECTED`. Requires a real, persisted Django user as `reviewer`; raises
    otherwise. Requires a non-empty `rationale`.
  - `mark_unmapped()` — records an explicit "no appropriate code exists"
    decision instead of guessing one.
  - `get_accepted_mappings()` / `get_accepted_codings()` — the only read
    path the FHIR export pipeline uses. Structurally cannot see anything
    but `ACCEPTED` rows.
- `admin.py` — the reviewable interface. A staff user opens a `PROPOSED` row
  and changes `status` to `ACCEPTED`/`REJECTED`; `save_model()` routes that
  transition through `review_mapping()`, so `reviewer`/`reviewed_at` are
  always the actual logged-in user and the actual save time — never
  hand-entered. Fields describing how a proposal originated
  (`source_*`, `mapping_method`, `confidence`) become read-only once a row
  exists, so a reviewer can correct a target code but not rewrite provenance.
- `views.py` / `urls.py` — read-only API at `/api/core/terminology-mappings/`,
  filterable by `status`/`source_system`/`source_code`/`target_terminology`,
  plus explicit `/terminology-mappings/proposed/` and `/accepted/` endpoints
  so the two lists are never confused with a forgotten query param.
- `management/commands/propose_terminology_mappings.py` — runs the semantic
  matcher against every `Indicator` and creates `PROPOSED` rows.

## Enforcement of "AI proposes, humans approve"

This isn't a convention enforced by code review alone — it's structural:

1. `propose_mapping()` hard-codes `status=PROPOSED` on every row it creates.
   There is no parameter that lets a caller set anything else.
2. `review_mapping()` is the only function anywhere in this app that writes
   `ACCEPTED`/`REJECTED`, and it requires a persisted `User` object. Nothing
   in `propose_terminology_mappings` or `suggest_mappings_for_indicator`
   calls it.
3. `apps/fhir/builders.py` never queries `TerminologyMapping` directly — it
   only ever receives pre-resolved codings from
   `get_accepted_codings()`, which filters on `status=ACCEPTED` at the ORM
   level. A `PROPOSED` or `REJECTED` mapping cannot reach an exported FHIR
   resource; see `apps/fhir/tests.py::BuildBundleTests.
   test_bundle_measure_carries_accepted_terminology_coding_only`.
4. A database constraint (`unique_accepted_mapping_per_source_and_terminology`)
   guarantees at most one `ACCEPTED` mapping per
   (`source_system`, `source_code`, `target_terminology`) — the FHIR
   pipeline can never face an ambiguous choice between two accepted codes.

## The "semantic search" matcher

`suggest_mappings_for_indicator()` scores an indicator's name against a
small, hand-curated table of real ICD-10 codes (`_ICD10_CANDIDATES` in
`services.py`) using `difflib.SequenceMatcher` — a deterministic, stdlib
string-similarity heuristic, not a live model/embedding call. This is a
deliberate transparency choice: the AI-transparency requirement is easier to
satisfy honestly with a small, inspectable heuristic than with a black-box
call dressed up as more authoritative than it is. Every candidate code in
the table is a real, verifiable ICD-10 code — the table is intentionally
tiny rather than attempting full coverage (building a terminology server or
auto-mapping every concept is explicitly out of scope for FR6.4).

## Where the code lands in FHIR

Per FHIR R4, `Measure` has no resource-level `.code` — the correct place for
"what concept is this measure/report actually about" is `Measure.group[].code`
/ `MeasureReport.group[].code` (both `CodeableConcept`, 0..1). `build_bundle()`
resolves accepted codings for the indicator and, if any exist, sets
`Measure.group[0].code` to a `CodeableConcept` whose `.coding` array holds one
entry per accepted terminology (system URI from `TERMINOLOGY_SYSTEM_URIS`,
e.g. `http://hl7.org/fhir/sid/icd-10`); `build_measure_report()` mirrors the
same `.code` onto the `MeasureReport.group[0]`, per FHIR convention that a
report should restate what its measure definition was measuring. If nothing
has been accepted yet, `.group` is omitted entirely rather than emitting an
empty/guessed code.

## Worked example (this repo's real data)

The only indicator currently ingested from the DHIS2 demo instance is
`fbfJHSPpUQD` / "ANC 1st visit". Running:

```
python manage.py propose_terminology_mappings
```

proposes `DHIS2:fbfJHSPpUQD → ICD-10 Z34.9` ("Encounter for supervision of
normal pregnancy, unspecified, trimester unspecified") at `PROPOSED` status,
method `semantic_search`, confidence `0.9`. A data steward reviews it in
Django admin (`Terminology mappings`) and flips `status` to `ACCEPTED`; only
then does `python manage.py export_fhir` produce a `Measure`/`MeasureReport`
carrying that ICD-10 coding.

`_ICD10_CANDIDATES` also includes `malaria → ICD-10 B50`, matching this
ticket's own worked example (`MALARIA_CASES` → `B50`) — illustrative rather
than tied to real ingested data, since no malaria indicator has been pulled
from DHIS2 in this environment.
