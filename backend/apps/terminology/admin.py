"""Django admin is the reviewable interface for terminology
mappings - the same pattern apps.data_products.admin.DataProductAdmin
already uses for governance decisions (sensitivity_classification etc.
are human-edited here, never inferred). A staff user opens a PROPOSED
row and changes its status to ACCEPTED/REJECTED; save_model() below
routes that transition through apps.terminology.services.review_mapping
so `reviewer`/`reviewed_at` are always the actual logged-in admin user
and the actual save time - never hand-entered, never left for the form
to fake.
"""
from django.contrib import admin
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .models import TerminologyMapping
from .services import review_mapping


@admin.register(TerminologyMapping)
class TerminologyMappingAdmin(admin.ModelAdmin):
    list_display = (
        'source_system', 'source_code', 'source_display', 'target_terminology',
        'target_code', 'status', 'mapping_method', 'confidence', 'reviewer', 'reviewed_at',
    )
    list_filter = ('status', 'target_terminology', 'mapping_method', 'source_system')
    search_fields = ('source_code', 'source_display', 'target_code', 'target_display')

    def get_readonly_fields(self, request, obj=None):
        readonly = ['reviewer', 'reviewed_at', 'created_at', 'updated_at']
        if obj is not None:
            # How/what was originally proposed stays immutable once a row
            # exists - a reviewer may correct the target code or rationale,
            # but not rewrite the provenance of where the proposal came from.
            readonly += ['source_system', 'source_code', 'source_display', 'mapping_method', 'confidence']
        return readonly

    def save_model(self, request, obj, form, change):
        original_status = TerminologyMapping.objects.get(pk=obj.pk).status if change else None
        status_changed = original_status != obj.status

        if status_changed and obj.status in (TerminologyMapping.Status.ACCEPTED, TerminologyMapping.Status.REJECTED):
            # Persists via review_mapping itself (full_clean + save), so the
            # generic super().save_model() below is skipped for this branch.
            review_mapping(
                obj, reviewer=request.user,
                approve=obj.status == TerminologyMapping.Status.ACCEPTED,
                rationale=obj.rationale,
            )
            record_event(
                AuditEvent.Action.ADMIN_CHANGE, AuditEvent.Outcome.SUCCESS,
                resource_type='TerminologyMapping', resource_id=obj.id,
                actor=request.user.username,
                detail={'status': obj.status},
            )
            return

        if status_changed and obj.status == TerminologyMapping.Status.UNMAPPED:
            obj.reviewer = request.user
            obj.reviewed_at = timezone.now()

        super().save_model(request, obj, form, change)
        record_event(
            AuditEvent.Action.ADMIN_CHANGE, AuditEvent.Outcome.SUCCESS,
            resource_type='TerminologyMapping', resource_id=obj.id,
            actor=request.user.username,
            detail={'changed_fields': form.changed_data},
        )
