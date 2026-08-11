"""Role-based authorisation for the mediation layer API.

Roles are plain Django ``Group`` rows (``data_provider``, ``analyst``,
``auditor`` - seeded by migration 0001_seed_role_groups). Assigning a user
to a role is done through the stock Django admin User change form's
"Groups" widget; no custom User model or extra app is needed for that.

This intentionally does not implement organisation/tenant scoping (a data
provider seeing only "their" org's records) - the assignment brief allows
"role-based OR organisation-aware authorisation", and role-based is the
simpler option it explicitly says is acceptable as long as the access
decisions are real, testable and documented (see docs/rbac.md).
"""
from rest_framework import permissions

DATA_PROVIDER = 'data_provider'
ANALYST = 'analyst'
AUDITOR = 'auditor'

ALL_ROLES = (DATA_PROVIDER, ANALYST, AUDITOR)


def HasAnyRole(*role_names):
    """Return a DRF permission class granting access to authenticated
    users who belong to at least one of ``role_names``.

    Django staff/superusers always pass, mirroring the ``IsAdminUser``
    behaviour this replaces - it's the operator escape hatch for whoever
    manages the system (e.g. to administer Groups themselves), not a
    fourth role.
    """

    class _HasAnyRole(permissions.BasePermission):
        def has_permission(self, request, view):
            user = getattr(request, 'user', None)
            if not (user and user.is_authenticated):
                return False
            if user.is_staff or user.is_superuser:
                return True
            return user.groups.filter(name__in=role_names).exists()

    _HasAnyRole.__name__ = f"HasAnyRole({', '.join(role_names)})"
    return _HasAnyRole
