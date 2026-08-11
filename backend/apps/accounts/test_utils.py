"""Shared setup for the role-permission tests in apps/dhis2, apps/fhir,
apps/terminology, apps/data_products and apps/accounts, so each app's
tests.py doesn't reimplement "create a user, put it in a role, get an
authenticated client".
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

_COUNTER = 0


class RoleTestMixin:
    def make_user(self, role=None, is_staff=False):
        global _COUNTER
        _COUNTER += 1
        user = get_user_model().objects.create_user(
            username=f'test-user-{_COUNTER}', password='x', is_staff=is_staff,
        )
        if role:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client
