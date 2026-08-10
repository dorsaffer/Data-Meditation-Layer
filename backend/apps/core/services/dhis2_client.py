"""DHIS2 analytics client.

FR1.1: connect to the official Sierra Leone demo.
FR1.2: retrieve aggregate indicators for districts/periods.

Read-only, source-specific extraction only — no transformation logic —
so this module can later be pointed at a different DHIS2 instance
without touching the rest of the pipeline. Never writes back to DHIS2.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 5


class DHIS2ClientError(Exception):
    """Any DHIS2 API failure. Message always includes the actual response
    body when one is available — DHIS2 error bodies (e.g. {"errorCode":
    "E7146", "message": "..."}) are the only way to debug a failed
    request, so a bare HTTP status is not enough.
    """


class DHIS2Client:
    def __init__(self, base_url=None, username=None, password=None, timeout=None):
        self.base_url = (base_url or settings.DHIS2_BASE_URL).rstrip('/')
        self.auth = (username or settings.DHIS2_USERNAME, password or settings.DHIS2_PASSWORD)
        self.timeout = timeout or settings.DHIS2_TIMEOUT_SECONDS

    def fetch_analytics(self, dx: list[str], ou: str, pe: str) -> list[dict]:
        """FR1.2: pull /api/analytics for the given data elements, org
        unit level/UID and period, and parse the compact table response
        into one plain dict per row.
        """
        url = f'{self.base_url}/api/analytics'
        params = {
            'dimension': [f'dx:{";".join(dx)}', f'ou:{ou}', f'pe:{pe}'],
            'displayProperty': 'NAME',
            'outputIdScheme': 'UID',
        }

        logged_url = requests.Request('GET', url, params=params).prepare().url
        logger.info('DHIS2 request: %s', logged_url)

        response = self._get_following_redirects(url, params)

        if not response.ok:
            raise DHIS2ClientError(
                f'DHIS2 returned HTTP {response.status_code} for {logged_url}: {response.text}'
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DHIS2ClientError(f'DHIS2 response was not valid JSON: {response.text[:500]}') from exc

        return self._parse_analytics(payload, source_url=logged_url)

    def _get_following_redirects(self, url: str, params: dict | None) -> requests.Response:
        """GET with redirects followed manually, re-attaching Basic Auth
        on every hop. Plain `requests`/`curl` drop the Authorization
        header on a cross-host redirect (security default), which breaks
        the official play.dhis2.org alias — it 302s to a versioned
        play.im.dhis2.org host on a different hostname.
        """
        with requests.Session() as session:
            for _ in range(MAX_REDIRECTS):
                try:
                    response = session.get(
                        url, params=params, auth=self.auth, timeout=self.timeout, allow_redirects=False
                    )
                except requests.exceptions.Timeout as exc:
                    raise DHIS2ClientError(f'Timed out calling {url}') from exc
                except requests.exceptions.ConnectionError as exc:
                    raise DHIS2ClientError(f'Could not connect to {url}') from exc
                except requests.exceptions.RequestException as exc:
                    raise DHIS2ClientError(f'Request to {url} failed: {exc}') from exc

                if response.is_redirect:
                    location = response.headers.get('Location')
                    if not location:
                        raise DHIS2ClientError(f'DHIS2 redirected {url} without a Location header')
                    url, params = location, None
                    continue
                return response

        raise DHIS2ClientError(f'Too many redirects resolving {url}')

    @staticmethod
    def _parse_analytics(payload: dict, source_url: str) -> list[dict]:
        headers = payload.get('headers', [])
        column = {h['name']: i for i, h in enumerate(headers)}
        for required in ('dx', 'ou', 'pe', 'value'):
            if required not in column:
                raise DHIS2ClientError(f'DHIS2 analytics response is missing expected column "{required}"')

        items = payload.get('metaData', {}).get('items', {})

        records = []
        for row in payload.get('rows', []):
            dx_uid = row[column['dx']]
            ou_uid = row[column['ou']]
            period = row[column['pe']]
            value = row[column['value']]
            records.append({
                'dx_uid': dx_uid,
                'dx_name': items.get(dx_uid, {}).get('name', dx_uid),
                'org_unit_uid': ou_uid,
                'org_unit_name': items.get(ou_uid, {}).get('name', ou_uid),
                'period': period,
                'value': value,
                'raw_payload': row,
                'source_url': source_url,
            })
        return records
