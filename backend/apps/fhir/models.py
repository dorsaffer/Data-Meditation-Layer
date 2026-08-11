from django.db import models


class FHIRValidationResult(models.Model):
    """Persisted conformity evidence for one generated FHIR
    resource — proof that the resource was actually checked against a
    real FHIR R4 server (see apps.fhir.services.validate_resource),
    never merely assumed valid because it "looks like" FHIR. One row
    per resource per export run, so history isn't overwritten and a
    later regression is visible.
    """

    resource_type = models.CharField(max_length=50)
    resource_reference = models.CharField(
        max_length=255,
        help_text='Human-readable pointer to what this resource represents, '
                   'e.g. "MeasureReport: ANC 1st visit / Bo / 202508".',
    )
    fhir_json = models.JSONField()
    fhir_release = models.CharField(max_length=10, default='R4')
    validator_used = models.CharField(max_length=255, default='HAPI FHIR JPA server ($validate)')
    is_valid = models.BooleanField()
    issues = models.JSONField(
        default=list, blank=True,
        help_text='OperationOutcome.issue entries returned by the validator.',
    )
    validated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-validated_at']

    def __str__(self):
        status = 'valid' if self.is_valid else 'INVALID'
        return f'{self.resource_type} ({self.resource_reference}) - {status}'
