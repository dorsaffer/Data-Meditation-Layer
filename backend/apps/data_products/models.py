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
    made through the admin form. governance_reviewed is likewise a
    human-only field (default False) - see apps.data_products.quality.
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
        PUBLISHABLE = 'publishable', 'Publishable'
        PUBLISHABLE_WITH_WARNINGS = 'publishable_with_warnings', 'Publishable with warnings'
        BLOCKED = 'blocked', 'Blocked'

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
        max_length=30, choices=QualityStatus.choices, default=QualityStatus.UNSCREENED
    )
    # M2M-to-roles would be premature: no Role model exists yet (RBAC is
    # a later phase). A list of role-name strings is the isolated,
    # documented MVP choice - swap for an M2M once roles are real.
    permitted_audience = models.JSONField(default=list, blank=True)
    # Nullable: most DataProducts are one-per-Indicator (sync_data_product),
    # but a cross-source, cross-indicator product (e.g. UHC District Service
    # Coverage, apps.population) has no single owning Indicator - forcing it
    # onto this FK would be wrong, not just awkward.
    indicator = models.ForeignKey(
        Indicator, on_delete=models.CASCADE, related_name='data_products', null=True, blank=True,
    )
    # Free-text methodology documentation for products that join more than
    # one source (see apps.population) - blank for ordinary single-source
    # products. Kept as plain text rather than structured fields since the
    # "how" varies per product and isn't something the API ever needs to
    # query on; DataProductSource below is the structured part (which
    # sources, when).
    join_strategy = models.TextField(
        blank=True, default='',
        help_text='How multiple sources were reconciled/joined (join key, unmatched handling).',
    )
    transformation_description = models.TextField(
        blank=True, default='',
        help_text='The transformation/formula applied, e.g. a derived metric definition.',
    )
    # Human-only governance gate, same "never inferred, human decision through
    # the admin form" pattern as sensitivity_classification/permitted_audience.
    # apps.data_products.quality reads this but never writes it - a data
    # steward must explicitly confirm review before a product can reach
    # publishable, no matter what the automated checks find.
    governance_reviewed = models.BooleanField(
        default=False,
        help_text='A data steward has reviewed sensitivity_classification and permitted_audience '
                   'for this product. Required before it can be marked publishable.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class DataProductSource(models.Model):
    """Retained provenance for one contributing source of a DataProduct.
    A single-source product (the common case) simply has zero or one of
    these; a joined product like UHC District Service Coverage has two.
    Deliberately generic (not population-specific) so any future
    multi-source product reuses this instead of growing more one-off
    fields on DataProduct itself.
    """

    data_product = models.ForeignKey(DataProduct, on_delete=models.CASCADE, related_name='sources')
    name = models.CharField(max_length=255, help_text='e.g. "Sierra Leone DHIS2" or the dataset\'s formal name.')
    description = models.TextField(blank=True, default='')
    extraction_date = models.DateField(
        null=True, blank=True, help_text='When this source was pulled/extracted, if applicable.',
    )
    reference_period = models.CharField(
        max_length=50, blank=True, default='',
        help_text='The period the source data itself refers to, e.g. "2021" for a census year.',
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.data_product.title} <- {self.name}'


class QualityCheckResult(models.Model):
    """One data-quality check's result for one DataProduct - the FR6.6
    "visible quality assessment" itself. Recomputed from scratch on every
    run of apps.data_products.quality.run_quality_checks() (same
    idempotent-recompute pattern as PopulationDataQualityIssue): never an
    accumulating log, always the current state.

    method distinguishes how much a human should trust an automated
    "passed" without re-checking it themselves: deterministic checks are
    hard facts (a regex match, a count, a DB constraint); heuristic
    checks are statistical judgement calls (e.g. an outlier threshold)
    that can have false positives/negatives; human_required checks are
    never actually evaluated by code - they read a decision a person
    already made (see DataProduct.governance_reviewed) and fail closed
    until that happens.
    """

    class Method(models.TextChoices):
        DETERMINISTIC = 'deterministic', 'Deterministic'
        HEURISTIC = 'heuristic', 'Heuristic'
        HUMAN_REQUIRED = 'human_required', 'Requires human approval'

    class Severity(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        BLOCKER = 'blocker', 'Blocker'

    data_product = models.ForeignKey(DataProduct, on_delete=models.CASCADE, related_name='quality_checks')
    check_code = models.CharField(max_length=50)
    check_name = models.CharField(max_length=255)
    method = models.CharField(max_length=20, choices=Method.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    passed = models.BooleanField()
    detail = models.TextField()
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.data_product.title} / {self.check_name}: {"pass" if self.passed else "fail"}'
