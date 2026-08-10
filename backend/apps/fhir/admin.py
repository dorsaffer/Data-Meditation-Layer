from django.contrib import admin

from .models import FHIRValidationResult


@admin.register(FHIRValidationResult)
class FHIRValidationResultAdmin(admin.ModelAdmin):
    list_display = ('resource_type', 'resource_reference', 'is_valid', 'fhir_release', 'validated_at')
    list_filter = ('resource_type', 'is_valid', 'fhir_release')
    search_fields = ('resource_reference',)
    readonly_fields = (
        'resource_type', 'resource_reference', 'fhir_json', 'fhir_release',
        'validator_used', 'is_valid', 'issues', 'validated_at',
    )
