from django.contrib import admin

from .models import DataProduct, DataProductSource, District, Indicator, Observation


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


@admin.register(DataProduct)
class DataProductAdmin(admin.ModelAdmin):
    """Governance fields (title, purpose, data_owner, source,
    geographic_coverage, schema_version, sensitivity_classification,
    permitted_audience, join_strategy, transformation_description) are
    editable here — that's the intended way to make the "restricted/
    admin-only" defaults a deliberate human decision. Pipeline-derived
    fields are read-only since sync_data_product() would just overwrite
    manual edits to them. join_strategy/transformation_description and
    the sources inline are relevant only to joined/multi-source products
    (see apps.population) - left blank for ordinary single-indicator ones.
    """
    list_display = (
        'title', 'indicator', 'transformation_status', 'quality_status',
        'sensitivity_classification', 'refresh_date',
    )
    list_filter = ('transformation_status', 'quality_status', 'sensitivity_classification')
    readonly_fields = (
        'refresh_date', 'temporal_coverage_start', 'temporal_coverage_end',
        'transformation_status', 'quality_status', 'updated_at',
    )
    inlines = [DataProductSourceInline]
