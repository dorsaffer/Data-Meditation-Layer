# Role-based authorisation

Implements the requirement to gate API access by role for at least
**data provider**, **authorised analyst** and **auditor**. This is the
"simpler implementation" the brief explicitly allows in place of Keycloak/
OAuth2/OIDC — role-based, not organisation-scoped — as long as the access
decisions are real (enforced server-side, not just hidden in the UI),
testable, and documented here.

## What a role is

A role is a plain Django `Group` row. Three groups exist, seeded
automatically by `apps/accounts/migrations/0001_seed_role_groups.py` so
they're present right after `python manage.py migrate`:

- `data_provider` — owns/submits the raw source data.
- `analyst` — works with the cleaned, canonical data and analytical views.
- `auditor` — read access across the pipeline for oversight/audit purposes.

No custom `User` model, no per-user "primary role" field, no organisation/
tenant model. A user can belong to more than one group if that's genuinely
true of them; the permission check is "does this user have *any* of the
roles this endpoint allows", not "what is this user's one role".

## Assigning a role to a user

Django admin → **Users** → open a user → **Groups** (multi-select widget) →
add them to `data_provider`, `analyst` and/or `auditor` → Save. No custom
admin code was needed for this — it's the stock `django.contrib.auth` User
change form.

## `is_staff` / superuser bypass

Django staff/superusers always pass every role check in this app. This is
an operator safety net (e.g. so whoever manages Groups via `/admin/` isn't
locked out of the API), the same precedent the codebase already used via
DRF's `IsAdminUser` before this change — it is **not** a fourth role, and
it's not organisation- or task-scoped.

## Identifying the current user's roles

`GET /api/auth/me/` (JWT-authenticated) returns:

```json
{"username": "analyst1", "roles": ["analyst"], "is_staff": false}
```

The frontend calls this right after login so it knows what to render
without probing individual endpoints for a 403.

## Endpoint → role matrix

| Endpoint | Allowed roles | Why |
|---|---|---|
| `GET /api/core/raw-records/` | `data_provider`, `auditor` | Raw ingestion, pre-screening — the submitting org and audit trail only. |
| `GET /api/core/observations/` | `analyst`, `auditor` | Cleaned analytical data points. |
| `GET /api/core/data-products/` | `data_provider`, `analyst`, `auditor` (any recognized role) | Catalog/governance metadata only — how any authorised party decides whether to request access to the underlying data. |
| `GET /api/core/fhir-validation-results/` | `analyst`, `auditor` | Conformity check results carry real aggregate values, gated the same as Observations. |
| `GET /api/core/terminology-mappings/`, `/proposed/`, `/accepted/` | `analyst`, `auditor` | Mapping catalog and its review trail. |

Every endpoint also requires plain authentication (a valid JWT); an
authenticated user with **no** matching role gets `403`, not `200` — e.g.
a logged-in account in no group cannot read `data-products` even though
that's the most broadly-readable endpoint.

## Running the tests that prove this

```
cd backend
python manage.py migrate
python manage.py test apps.accounts apps.dhis2 apps.data_products apps.fhir apps.terminology
```

Each of the four data-serving apps has a permission test class asserting,
per endpoint: `200` for every allowed role and for staff, `403` for a
disallowed role and for a no-role account, `401` for anonymous. `apps/
accounts/tests.py` covers `MeView` directly. `apps/accounts/test_utils.py`
holds the shared `RoleTestMixin` (`make_user(role=..., is_staff=...)`,
`client_for(user)`) all of these reuse.

## Known limitation

This is role-based, not organisation-scoped: a `data_provider` sees *all*
raw records, not only the ones their own organisation submitted, because
there's no organisation/tenant model in the data yet (`DataProduct.
data_owner` is a free-text field, not a foreign key). The brief permits
this simplification explicitly ("role-based **or** organisation-aware").
Adding real per-organisation scoping would mean introducing an
Organisation model and FKs from the ingestion/product models to it — a
larger change than this pass covers.
