from django.contrib import admin

from apps.audit.context import audit_context
from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .models import DataProduct, DataProductSource, District, Indicator, Observation, QualityCheckResult
from .quality import run_quality_checks


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'dhis2_org_unit_uid')
    search_fields = ('name', 'dhis2_org_unit_uid')


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('name', 'dhis2_dx_uid')
    search_fields = ('name', 'dhis2_dx_uid')


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ('indicator', 'district', 'period', 'value')
    list_filter = ('indicator', 'district')
    search_fields = ('period',)
    readonly_fields = ('indicator', 'district', 'period', 'value', 'source_raw_record')


class DataProductSourceInline(admin.TabularInline):
    model = DataProductSource
    extra = 0


class QualityCheckResultInline(admin.TabularInline):
    model = QualityCheckResult
    extra = 0
    fields = ('check_name', 'method', 'severity', 'passed', 'detail', 'checked_at')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DataProduct)
class DataProductAdmin(admin.ModelAdmin):
    """Governance fields (title, purpose, data_owner, source,
    geographic_coverage, schema_version, sensitivity_classification,
    permitted_audience, join_strategy, transformation_description,
    governance_reviewed) are editable here — that's the intended way to
    make the "prohibited/no-audience" default, and the FR6.6/FR6.7 human
    sign-off, a deliberate human decision. Pipeline-derived fields are
    read-only since sync_data_product()/run_quality_checks() would just
    overwrite manual edits to them. join_strategy/transformation_description
    and the sources inline are relevant only to joined/multi-source
    products (see apps.population) - left blank for ordinary
    single-indicator ones.
    """
    list_display = (
        'title', 'indicator', 'transformation_status', 'quality_status',
        'governance_reviewed', 'sensitivity_classification', 'refresh_date',
    )
    list_filter = ('transformation_status', 'quality_status', 'governance_reviewed', 'sensitivity_classification')
    readonly_fields = (
        'refresh_date', 'temporal_coverage_start', 'temporal_coverage_end',
        'transformation_status', 'quality_status', 'updated_at',
    )
    inlines = [DataProductSourceInline, QualityCheckResultInline]
    actions = ['recompute_quality_checks']

    def save_model(self, request, obj, form, change):
        """FR6.8: every hand-edit of governance metadata through this form
        (sensitivity_classification, permitted_audience, governance_reviewed,
        etc.) is an ADMIN_CHANGE - the same "actor is the real logged-in
        user" pattern apps.terminology.admin.TerminologyMappingAdmin
        already uses for its own review actions.
        """
        super().save_model(request, obj, form, change)
        record_event(
            AuditEvent.Action.ADMIN_CHANGE, AuditEvent.Outcome.SUCCESS,
            resource_type='DataProduct', resource_id=obj.id,
            actor=request.user.username,
            detail={'changed_fields': form.changed_data},
        )

    @admin.action(description='Recompute FR6.6/FR6.7 quality & privacy assessment')
    def recompute_quality_checks(self, request, queryset):
        with audit_context(actor=request.user.username):
            for product in queryset:
                run_quality_checks(product)
        self.message_user(request, f'Recomputed quality checks for {queryset.count()} data product(s).')
