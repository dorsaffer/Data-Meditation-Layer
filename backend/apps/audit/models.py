"""FR6.8: the audit trail.

Two distinct tables, deliberately not merged into one, because they
answer different questions for different readers:

- ``AuditEvent`` — *who did what to the system, and were they allowed
  to.* Security/access activity: logins, denied access, viewing/
  downloading data, and the pipeline/publication actions a person or
  service triggered. This is what an auditor reviews to investigate
  "who accessed dataset X on date Y".
- ``ProvenanceRecord`` — *how a dataset's content came to be.* Data
  lineage: which source it was acquired from, how it was transformed,
  what it was derived/joined from. This is what someone reviews to
  answer "where did this number in DataProduct X come from", regardless
  of who was looking at the system when it happened. It complements
  (doesn't replace) the static provenance metadata that already exists
  on DataProduct/DataProductSource (data_owner, source, join_strategy,
  Observation.source_raw_record) - those describe the *current* lineage;
  ProvenanceRecord is a timestamped log of *when* each transformation
  activity ran.

See docs/audit.md for the full usage guide and the worked example this
docstring is deliberately kept short in favour of.
"""
from __future__ import annotations

from django.db import models


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        AUTHENTICATION = 'authentication', 'Authentication attempt'
        ACCESS_DENIED = 'access_denied', 'Access denied'
        DATA_ACQUISITION = 'data_acquisition', 'Data acquisition'
        DATA_TRANSFORMATION = 'data_transformation', 'Data transformation'
        DATA_VALIDATION = 'data_validation', 'Data validation'
        DATASET_PUBLICATION = 'dataset_publication', 'Dataset publication'
        DATASET_VIEW = 'dataset_view', 'Dataset viewing'
        DATASET_DOWNLOAD = 'dataset_download', 'Dataset downloading'
        ADMIN_CHANGE = 'admin_change', 'Administrative change'

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Success'
        DENIED = 'denied', 'Denied'
        FAILURE = 'failure', 'Failure'

    actor = models.CharField(
        max_length=150,
        help_text='Username for a request-triggered action, or a "system:<command>" label '
                   'for an unattended pipeline run - never blank.',
    )
    # Free-text, same simplification apps.data_products.models.DataProduct.data_owner
    # already uses - no Organisation/tenant model exists yet (see docs/rbac.md's
    # "Known limitation"). Left blank when no organisation is known for the actor.
    organisation = models.CharField(max_length=255, blank=True, default='')
    action = models.CharField(max_length=30, choices=Action.choices)
    resource_type = models.CharField(max_length=100, blank=True, default='')
    resource_id = models.CharField(max_length=100, blank=True, default='')
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    correlation_id = models.CharField(max_length=36, db_index=True)
    # Non-sensitive contextual metadata only (query params, row counts, decision
    # codes) - never raw payloads, free-text governance fields, or anything that
    # could itself leak the data being described. See docs/audit.md.
    detail = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
        ]

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.actor} {self.action} {self.outcome}'

    def save(self, *args, **kwargs):
        # Append-only: a real audit trail must not be editable after the
        # fact through normal application code. This is the model-level
        # backstop; the API only ever exposes a ReadOnlyModelViewSet and
        # the admin registration has no change/delete permission either
        # (defence in depth, not redundant - each layer covers a
        # different way of touching the table).
        if self.pk is not None:
            raise ValueError('AuditEvent records are append-only and cannot be modified after creation.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('AuditEvent records cannot be deleted through the application.')


class ProvenanceRecord(models.Model):
    class Activity(models.TextChoices):
        ACQUIRED = 'acquired', 'Acquired from source'
        TRANSFORMED = 'transformed', 'Transformed to canonical model'
        VALIDATED = 'validated', 'Validated'
        DERIVED = 'derived', 'Derived/joined from other datasets'

    # Nullable: a provenance entry can describe activity on a resource that
    # doesn't have (or doesn't yet have) an owning DataProduct - e.g. the raw
    # acquisition step, which runs before any DataProduct exists.
    data_product = models.ForeignKey(
        'data_products.DataProduct', on_delete=models.CASCADE,
        related_name='provenance_records', null=True, blank=True,
    )
    resource_type = models.CharField(max_length=100, blank=True, default='')
    resource_id = models.CharField(max_length=100, blank=True, default='')
    activity = models.CharField(max_length=20, choices=Activity.choices)
    description = models.TextField()
    source_reference = models.CharField(
        max_length=255, blank=True, default='',
        help_text='What this activity read from, e.g. a DHIS2 dx/org-unit/period slice.',
    )
    performed_by = models.CharField(max_length=150)
    correlation_id = models.CharField(max_length=36, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.get_activity_display()} — {self.description[:60]}'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('ProvenanceRecord rows are append-only and cannot be modified after creation.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('ProvenanceRecord rows cannot be deleted through the application.')
