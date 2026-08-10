from django.db import models


class RawDHIS2Record(models.Model):
    """FR1.3: one unmodified DHIS2 analytics data point — the
    traceability anchor everything downstream points back to. Never
    edited directly; only ever added/refreshed via fetch_dhis2_data's
    update_or_create on (dx_uid, org_unit_uid, period).
    """

    dx_uid = models.CharField(max_length=50)
    dx_name = models.CharField(max_length=255)
    org_unit_uid = models.CharField(max_length=50)
    org_unit_name = models.CharField(max_length=255)
    period = models.CharField(max_length=20)
    value = models.CharField(max_length=50)
    raw_payload = models.JSONField()
    source_url = models.URLField(max_length=500)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['dx_uid', 'org_unit_uid', 'period'],
                name='unique_dhis2_record_dx_ou_period',
            )
        ]
        ordering = ['org_unit_name', 'dx_name', 'period']

    def __str__(self):
        return f'{self.dx_name} / {self.org_unit_name} / {self.period} = {self.value}'
