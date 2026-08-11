from django.test import TestCase

from apps.accounts.permissions import ANALYST
from apps.accounts.test_utils import RoleTestMixin


class MeViewTests(RoleTestMixin, TestCase):
    def test_returns_username_roles_and_staff_flag(self):
        user = self.make_user(role=ANALYST)
        response = self.client_for(user).get('/api/auth/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], user.username)
        self.assertEqual(response.data['roles'], [ANALYST])
        self.assertFalse(response.data['is_staff'])

    def test_user_with_no_group_gets_empty_roles_list(self):
        user = self.make_user()
        response = self.client_for(user).get('/api/auth/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['roles'], [])

    def test_is_staff_reflected(self):
        user = self.make_user(is_staff=True)
        response = self.client_for(user).get('/api/auth/me/')

        self.assertTrue(response.data['is_staff'])

    def test_anonymous_request_is_rejected(self):
        from rest_framework.test import APIClient

        response = APIClient().get('/api/auth/me/')
        self.assertEqual(response.status_code, 401)
