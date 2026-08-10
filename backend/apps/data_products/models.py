from django.db import models


class District(models.Model):
    """Resolved, human-readable DHIS2 org unit — canonical, decoupled
    from the raw DHIS2 shape."""

    dhis2_org_unit_uid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Indicator(models.Model):
    """Resolved, human-readable DHIS2 data element."""

    dhis2_dx_uid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return self.name


class Observation(models.Model):
    """FR2: a single clean data point. Always keeps a link back to the
    exact RawDHIS2Record it was cast from, so a clean number can always
    be traced to precisely what DHIS2 originally returned.
    """

    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='observations')
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='observations')
    period = models.CharField(max_length=20)
    value = models.FloatField()
    source_raw_record = models.ForeignKey(
        'dhis2.RawDHIS2Record', on_delete=models.PROTECT, related_name='observations'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['indicator', 'district', 'period'],
                name='unique_observation_indicator_district_period',
            )
        ]
        ordering = ['district__name', 'indicator__name', 'period']

    def __str__(self):
        return f'{self.indicator.name} / {self.district.name} / {self.period} = {self.value}'


class DataProduct(models.Model):
    """Governance metadata about a set of Observations for one
    indicator — not the data itself. Self-describing: what it is, where
    it came from, how trustworthy it is, who may see it.

    sensitivity_classification and permitted_audience are governance
    judgement calls and are deliberately never inferred from the data —
    sync_data_product() only ever touches the pipeline-derived fields
    (refresh_date, temporal_coverage_*, transformation_status,
    quality_status); on first creation it defaults to the most
    conservative values (restricted / admin-only) precisely so nothing
    gets silently treated as "safe to share" without a human decision
    made through the admin form.
    """

    class SensitivityClassification(models.TextChoices):
        PUBLIC = 'public', 'Public'
        RESTRICTED = 'restricted', 'Restricted'
        CONFIDENTIAL = 'confidential', 'Confidential'

    class TransformationStatus(models.TextChoices):
        RAW_ONLY = 'raw_only', 'Raw only'
        CANONICAL = 'canonical', 'Canonical'
        FHIR_MAPPED = 'fhir_mapped', 'FHIR mapped'

    class QualityStatus(models.TextChoices):
        UNSCREENED = 'unscreened', 'Unscreened'
        PASSED = 'passed', 'Passed'
        FLAGGED = 'flagged', 'Flagged'

    title = models.CharField(max_length=255)
    purpose = models.TextField(blank=True, default='')
    data_owner = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=255, blank=True, default='')
    refresh_date = models.DateTimeField(null=True, blank=True)
    geographic_coverage = models.CharField(max_length=255, blank=True, default='')
    temporal_coverage_start = models.CharField(max_length=20, blank=True, default='')
    temporal_coverage_end = models.CharField(max_length=20, blank=True, default='')
    schema_version = models.CharField(max_length=20, default='1.0')
    sensitivity_classification = models.CharField(
        max_length=20, choices=SensitivityClassification.choices,
        default=SensitivityClassification.RESTRICTED,
    )
    transformation_status = models.CharField(
        max_length=20, choices=TransformationStatus.choices, default=TransformationStatus.RAW_ONLY
    )
    quality_status = models.CharField(
        max_length=20, choices=QualityStatus.choices, default=QualityStatus.UNSCREENED
    )
    # M2M-to-roles would be premature: no Role model exists yet (RBAC is
    # a later phase). A list of role-name strings is the isolated,
    # documented MVP choice - swap for an M2M once roles are real.
    permitted_audience = models.JSONField(default=list, blank=True)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='data_products')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
